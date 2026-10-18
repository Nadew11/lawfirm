"""Step 1 tests: deterministic replication of claimed values."""
from __future__ import annotations

import math

import numpy as np
import pytest

from cmpm.config_loader import load_config
from cmpm.economics import (
    breakeven_benefit,
    compute_discounted_payback,
    compute_irr,
    compute_npv,
    compute_simple_payback,
)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


# -----------------------------------------------------------------------
# Claimed values (from the problem statement)
# -----------------------------------------------------------------------
CLAIMED = {
    "lab_ventilation":       {"npv": 633_000, "payback": 2.15, "irr": 0.45},
    "central_plant":         {"npv": 1_118_000, "payback": 3.64, "irr": 0.24},
    "classroom_bas":         {"npv": 241_000, "payback": 3.00, "irr": 0.31},
    "electrical_monitoring": {"npv": 300_000, "payback": 3.78, "irr": 0.23},  # v2: benefit = $92.5k
    "dorm_occupancy":        {"npv": 166_000, "payback": 4.00, "irr": 0.21},
}

NPV_TOL = 5_000
PAYBACK_TOL = 0.02
IRR_TOL = 0.015


class TestNPVReplication:
    """Verify computed NPVs match claimed values within tolerance."""

    @pytest.mark.parametrize("project_key", CLAIMED.keys())
    def test_npv(self, cfg, project_key):
        p = cfg["projects"][project_key]
        rate = cfg["general"]["discount_rate"]
        life = cfg["general"]["analysis_life_years"]
        npv = compute_npv(p["capex"], p["annual_benefit"], rate, life)
        claimed = CLAIMED[project_key]["npv"]
        delta = abs(npv - claimed)
        assert delta < NPV_TOL, (
            f"FAIL {project_key}: NPV={npv:.0f}, claimed={claimed}, delta={delta:.0f}"
        )


class TestPaybackReplication:
    """Verify simple payback matches claimed values."""

    @pytest.mark.parametrize("project_key", CLAIMED.keys())
    def test_payback(self, cfg, project_key):
        p = cfg["projects"][project_key]
        pb = compute_simple_payback(p["capex"], p["annual_benefit"])
        claimed = CLAIMED[project_key]["payback"]
        delta = abs(pb - claimed)
        assert delta < PAYBACK_TOL, (
            f"FAIL {project_key}: payback={pb:.4f}, claimed={claimed}, delta={delta:.4f}"
        )


class TestIRRReplication:
    """Verify IRR matches claimed values."""

    @pytest.mark.parametrize("project_key", CLAIMED.keys())
    def test_irr(self, cfg, project_key):
        p = cfg["projects"][project_key]
        life = cfg["general"]["analysis_life_years"]
        irr = compute_irr(p["capex"], p["annual_benefit"], life)
        claimed = CLAIMED[project_key]["irr"]
        delta = abs(irr - claimed)
        assert delta < IRR_TOL, (
            f"FAIL {project_key}: IRR={irr:.4f}, claimed={claimed}, delta={delta:.4f}"
        )


class TestBreakEven:
    """Break-even analysis: benefit where NPV=0, and breakeven rate = IRR."""

    @pytest.mark.parametrize("project_key", CLAIMED.keys())
    def test_breakeven_benefit(self, cfg, project_key):
        p = cfg["projects"][project_key]
        rate = cfg["general"]["discount_rate"]
        life = cfg["general"]["analysis_life_years"]
        be = breakeven_benefit(p["capex"], rate, life)
        npv_at_be = compute_npv(p["capex"], be, rate, life)
        assert abs(npv_at_be) < 1.0, (
            f"FAIL {project_key}: NPV at breakeven benefit = {npv_at_be:.2f}"
        )

    @pytest.mark.parametrize("project_key", CLAIMED.keys())
    def test_breakeven_rate_equals_irr(self, cfg, project_key):
        p = cfg["projects"][project_key]
        life = cfg["general"]["analysis_life_years"]
        irr = compute_irr(p["capex"], p["annual_benefit"], life)
        npv_at_irr = compute_npv(
            p["capex"], p["annual_benefit"], irr, life, cross_check=False
        )
        assert abs(npv_at_irr) < 1.0, (
            f"FAIL {project_key}: NPV at IRR={irr:.4f} = {npv_at_irr:.2f}"
        )


class TestLabSensitivity:
    """Lab ventilation sensitivity table: savings +/-20%, discount 4%/10%, capex +20%."""

    def test_savings_minus_20(self, cfg):
        p = cfg["projects"]["lab_ventilation"]
        rate = cfg["general"]["discount_rate"]
        life = cfg["general"]["analysis_life_years"]
        npv = compute_npv(p["capex"], p["annual_benefit"] * 0.80, rate, life, cross_check=False)
        assert npv > 0

    def test_savings_plus_20(self, cfg):
        p = cfg["projects"]["lab_ventilation"]
        rate = cfg["general"]["discount_rate"]
        life = cfg["general"]["analysis_life_years"]
        npv = compute_npv(p["capex"], p["annual_benefit"] * 1.20, rate, life, cross_check=False)
        assert npv > 0

    def test_discount_4pct(self, cfg):
        p = cfg["projects"]["lab_ventilation"]
        life = cfg["general"]["analysis_life_years"]
        npv = compute_npv(p["capex"], p["annual_benefit"], 0.04, life, cross_check=False)
        assert npv > 0

    def test_discount_10pct(self, cfg):
        p = cfg["projects"]["lab_ventilation"]
        life = cfg["general"]["analysis_life_years"]
        npv = compute_npv(p["capex"], p["annual_benefit"], 0.10, life, cross_check=False)
        assert npv > 0

    def test_capex_plus_20(self, cfg):
        p = cfg["projects"]["lab_ventilation"]
        rate = cfg["general"]["discount_rate"]
        life = cfg["general"]["analysis_life_years"]
        npv = compute_npv(p["capex"] * 1.20, p["annual_benefit"], rate, life, cross_check=False)
        assert npv > 0


class TestDiscountedPayback:
    """Discounted payback should be >= simple payback for positive discount rates."""

    @pytest.mark.parametrize("project_key", CLAIMED.keys())
    def test_discounted_ge_simple(self, cfg, project_key):
        p = cfg["projects"][project_key]
        rate = cfg["general"]["discount_rate"]
        life = cfg["general"]["analysis_life_years"]
        simple = compute_simple_payback(p["capex"], p["annual_benefit"])
        discounted = compute_discounted_payback(
            p["capex"], p["annual_benefit"], rate, life
        )
        assert discounted >= simple - 0.01, (
            f"FAIL {project_key}: discounted={discounted:.2f} < simple={simple:.2f}"
        )

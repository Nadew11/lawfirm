"""Step 4 tests: interaction math and subset enumeration."""
from __future__ import annotations

import pytest

from cmpm.config_loader import load_config
from cmpm.interactions import (
    adjusted_benefit,
    adjusted_portfolio_npv,
    enumerate_all_subsets,
    interaction_matrix_from_config,
    naive_portfolio_npv,
    sequencing_analysis,
)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


class TestInteractionMatrix:
    def test_parses_config(self, cfg):
        mat = interaction_matrix_from_config(cfg)
        assert ("lab_ventilation", "central_plant") in mat
        assert mat[("lab_ventilation", "central_plant")] == 0.10  # v2: lowered from 0.15

    def test_classroom_interaction(self, cfg):
        mat = interaction_matrix_from_config(cfg)
        assert ("classroom_bas", "central_plant") in mat
        assert mat[("classroom_bas", "central_plant")] == 0.03  # v2: lowered from 0.05

    def test_new_interactions_present(self, cfg):
        mat = interaction_matrix_from_config(cfg)
        assert ("lab_ventilation", "classroom_bas") in mat
        assert ("dorm_occupancy", "central_plant") in mat


class TestAdjustedBenefit:
    def test_no_interaction_unchanged(self, cfg):
        projects = cfg["projects"]
        mat = interaction_matrix_from_config(cfg)
        # dorm -> lab has no interaction in config
        ab = adjusted_benefit("lab_ventilation", ["lab_ventilation", "dorm_occupancy"], projects, mat)
        assert ab == projects["lab_ventilation"]["annual_benefit"]

    def test_plant_reduced_by_lab(self, cfg):
        projects = cfg["projects"]
        mat = interaction_matrix_from_config(cfg)
        ab = adjusted_benefit("central_plant", ["central_plant", "lab_ventilation"], projects, mat)
        expected = projects["central_plant"]["annual_benefit"] * 0.90  # v2: 10% reduction
        assert abs(ab - expected) < 1.0

    def test_plant_reduced_by_both(self, cfg):
        projects = cfg["projects"]
        mat = interaction_matrix_from_config(cfg)
        selected = ["central_plant", "lab_ventilation", "classroom_bas"]
        ab = adjusted_benefit("central_plant", selected, projects, mat)
        expected = projects["central_plant"]["annual_benefit"] * 0.87  # v2: 10% + 3% = 13%
        assert abs(ab - expected) < 1.0


class TestSubsetEnumeration:
    def test_all_subsets(self, cfg):
        df = enumerate_all_subsets(cfg)
        n = len(cfg["projects"])
        assert len(df) == (2 ** n) - 1  # all non-empty subsets

    def test_overstatement_nonneg(self, cfg):
        df = enumerate_all_subsets(cfg)
        assert (df["overstatement"] >= -0.01).all()

    def test_single_projects_no_overstatement(self, cfg):
        df = enumerate_all_subsets(cfg)
        singles = df[df["size"] == 1]
        assert (singles["overstatement"].abs() < 1.0).all()


class TestSequencing:
    def test_produces_rows(self, cfg):
        df = sequencing_analysis(cfg)
        assert len(df) == 3  # plant_first, plant_last, simultaneous

    def test_plant_first_vs_last_differ(self, cfg):
        df = sequencing_analysis(cfg)
        pf = df[df["sequence"] == "plant_first"]["npv"].iloc[0]
        pl = df[df["sequence"] == "plant_last"]["npv"].iloc[0]
        assert pf != pl


class TestNaiveVsAdjusted:
    def test_naive_ge_adjusted(self, cfg):
        projects = cfg["projects"]
        rate = cfg["general"]["discount_rate"]
        life = cfg["general"]["analysis_life_years"]
        mat = interaction_matrix_from_config(cfg)
        all_keys = list(projects.keys())
        naive = naive_portfolio_npv(all_keys, projects, rate, life)
        adjusted = adjusted_portfolio_npv(all_keys, projects, mat, rate, life)
        assert naive >= adjusted - 1.0

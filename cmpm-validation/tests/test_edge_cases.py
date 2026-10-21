"""Edge-case tests: zero benefit, negative CFs, IRR with no sign change."""
from __future__ import annotations

import math

import numpy as np
import pytest

from cmpm.economics import (
    compute_discounted_payback,
    compute_irr,
    compute_npv,
    compute_simple_payback,
)


class TestZeroBenefit:
    def test_npv_is_neg_capex(self):
        npv = compute_npv(100_000, 0, 0.07, 10, cross_check=False)
        assert abs(npv - (-100_000)) < 1.0

    def test_payback_is_inf(self):
        pb = compute_simple_payback(100_000, 0)
        assert math.isinf(pb)

    def test_irr_is_nan(self):
        irr = compute_irr(100_000, 0, 10)
        assert np.isnan(irr)


class TestNegativeBenefit:
    def test_npv_strongly_negative(self):
        npv = compute_npv(100_000, -10_000, 0.07, 10, cross_check=False)
        assert npv < -100_000

    def test_payback_is_inf(self):
        pb = compute_simple_payback(100_000, -10_000)
        assert math.isinf(pb)

    def test_irr_is_nan(self):
        irr = compute_irr(100_000, -10_000, 10)
        assert np.isnan(irr)


class TestSingleYearLife:
    def test_npv(self):
        npv = compute_npv(100_000, 200_000, 0.07, 1, cross_check=False)
        expected = -100_000 + 200_000 / 1.07
        assert abs(npv - expected) < 1.0

    def test_irr(self):
        irr = compute_irr(100_000, 200_000, 1)
        assert abs(irr - 1.0) < 0.01


class TestZeroDiscountRate:
    def test_npv_is_sum(self):
        npv = compute_npv(100_000, 50_000, 0.0, 10, cross_check=False)
        expected = -100_000 + 50_000 * 10
        assert abs(npv - expected) < 1.0


class TestNoSignChange:
    def test_all_positive_irr_nan(self):
        irr = compute_irr(0, 50_000, 10)
        assert np.isnan(irr)

    def test_discounted_payback_inf_when_benefit_too_small(self):
        dpb = compute_discounted_payback(1_000_000, 10_000, 0.07, 5)
        assert math.isinf(dpb)

"""The scenario-config validators reject malformed input after relocation.

`validate_config` and `validate_all_numeric_positive` moved out of the deleted
`utils/helpers.py` into `config/base_config.py` (utils-cleanup issue 02). The
relocation also dropped `validate_tuple`'s exclude-std-then-recheck-it dance, so
the failure mode these tests guard is: a config tuple with a NEGATIVE standard
deviation must still be rejected, and the generic validators must still raise
ValueError on bad input rather than passing it through.

Each test is proven non-vacuous: feeding the *valid* counterpart does not raise,
so the assertion is exercising the reject branch, not a blanket failure.
"""

import pytest

from config.base_config import (
    validate_all_numeric_positive,
    validate_config,
    validate_tuple,
)


def test_validate_tuple_rejects_negative_std():
    """Guards the redundancy resolution: removing the manual `_std < 0` recheck
    must NOT stop a negative std from being caught -- allow_zero=True validation
    of the std field has to keep doing that job."""
    # Non-vacuity: a valid (mean, std) with std == 0 passes the same path.
    validate_tuple((1.0, 0.0), "Waste generation")

    with pytest.raises(ValueError):
        validate_tuple((1.0, -0.1), "Waste generation")


def test_validate_all_numeric_positive_rejects_negative_when_zero_allowed():
    """allow_zero=True means non-negative: zero passes, a negative value raises."""
    validate_all_numeric_positive({"x": 0.0}, allow_zero=True)

    with pytest.raises(ValueError):
        validate_all_numeric_positive({"x": -1.0}, allow_zero=True)


def test_validate_all_numeric_positive_rejects_zero_when_disallowed():
    """Default allow_zero=False means strictly positive: zero must raise."""
    validate_all_numeric_positive({"x": 1.0})

    with pytest.raises(ValueError):
        validate_all_numeric_positive({"x": 0.0})


def test_validate_all_numeric_positive_rejects_non_number():
    """A non-numeric value is rejected before the sign comparison."""
    validate_all_numeric_positive({"x": 1.0})

    with pytest.raises(ValueError):
        validate_all_numeric_positive({"x": "not a number"})


def test_validate_config_wraps_validator_failure_as_value_error():
    """The generic wrapper turns any validator exception into ValueError; a
    passing validator returns without raising."""
    validate_config(object(), lambda _c: None, "thing")

    def _always_fails(_c):
        raise KeyError("boom")

    with pytest.raises(ValueError):
        validate_config(object(), _always_fails, "thing")

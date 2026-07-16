import pytest

from app.models import PriceRule, calculate_target_price


def test_price_rule_rounds_up_and_keeps_margin() -> None:
    assert calculate_target_price(3980, PriceRule(markup=1.18, fixed_fee=300, minimum_margin=300)) == 5000


def test_price_requires_positive_value() -> None:
    with pytest.raises(ValueError):
        calculate_target_price(None, PriceRule())

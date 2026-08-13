import pytest

from app.models import PriceRule, calculate_target_price


def test_price_rule_rounds_up_and_keeps_margin() -> None:
    assert (
        calculate_target_price(
            3980,
            PriceRule(markup=1.18, fixed_fee=300, minimum_margin=300),
        )
        == 5000
    )


def test_price_rule_handles_fx_fee_shipping_and_rounding() -> None:
    price = calculate_target_price(
        1000,
        PriceRule(
            markup=1.1,
            fixed_fee=0,
            minimum_margin=100,
            fx_rate=0.25,
            marketplace_fee_rate=0.1,
            shipping_cost=50,
            rounding_step=10,
        ),
    )
    assert price == 450


def test_price_requires_positive_value() -> None:
    with pytest.raises(ValueError):
        calculate_target_price(None, PriceRule())

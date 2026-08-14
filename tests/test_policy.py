from app.models import ProductRecord
from app.policy import ShopeeProductPolicy


def test_blacklist_denies_weapon() -> None:
    policy = ShopeeProductPolicy("data/shopee_blacklist.json", strict=True)
    decision = policy.evaluate(
        ProductRecord(
            asin="B012345678", title="Tactical gun ammunition holder", price=1000
        ),
        "SG",
    )
    assert decision.allowed is False
    assert decision.level == "deny"


def test_strict_policy_blocks_review_item() -> None:
    policy = ShopeeProductPolicy("data/shopee_blacklist.json", strict=True)
    decision = policy.evaluate(
        ProductRecord(
            asin="B012345679", title="Lithium battery power bank", price=1000
        ),
        "MY",
    )
    assert decision.allowed is False
    assert decision.level == "review"


def test_market_override_blocks_ph_contact_lens() -> None:
    policy = ShopeeProductPolicy("data/shopee_blacklist.json", strict=True)
    decision = policy.evaluate(
        ProductRecord(asin="B012345671", title="Colored contact lens set", price=1000),
        "PH",
    )
    assert decision.allowed is False
    assert any("ph_preferred_prohibited" in reason for reason in decision.reasons)


def test_low_risk_stationery_is_allowed() -> None:
    policy = ShopeeProductPolicy("data/shopee_blacklist.json", strict=True)
    decision = policy.evaluate(
        ProductRecord(asin="B012345672", title="A5 notebook file organizer", price=1000),
        "SG",
    )
    assert decision.allowed is True


def test_unknown_market_fails_closed() -> None:
    policy = ShopeeProductPolicy("data/shopee_blacklist.json", strict=True)
    decision = policy.evaluate(
        ProductRecord(asin="B012345670", title="Plain notebook", price=1000), ""
    )
    assert decision.allowed is False

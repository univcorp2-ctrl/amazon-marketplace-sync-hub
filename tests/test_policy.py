from app.models import ProductRecord
from app.policy import ShopeeProductPolicy


def test_blacklist_denies_weapon() -> None:
    policy = ShopeeProductPolicy("data/shopee_blacklist.json", strict=True)
    decision = policy.evaluate(ProductRecord(asin="B012345678", title="Tactical gun ammunition holder", price=1000), "SG")
    assert decision.allowed is False
    assert decision.level == "deny"


def test_strict_policy_blocks_review_item() -> None:
    policy = ShopeeProductPolicy("data/shopee_blacklist.json", strict=True)
    decision = policy.evaluate(ProductRecord(asin="B012345679", title="Lithium battery power bank", price=1000), "MY")
    assert decision.allowed is False
    assert decision.level == "review"


def test_unknown_market_fails_closed() -> None:
    policy = ShopeeProductPolicy("data/shopee_blacklist.json", strict=True)
    decision = policy.evaluate(ProductRecord(asin="B012345670", title="Plain notebook", price=1000), "")
    assert decision.allowed is False

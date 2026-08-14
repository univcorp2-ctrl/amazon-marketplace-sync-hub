from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models import ProductRecord


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    level: str
    reasons: list[str]
    matched_terms: list[str]


class ShopeeProductPolicy:
    def __init__(
        self,
        policy_path: str = "data/shopee_blacklist.json",
        *,
        strict: bool = True,
    ) -> None:
        path = Path(policy_path)
        if not path.exists():
            raise RuntimeError(f"Shopee policy file is missing: {path}")
        self.data = json.loads(path.read_text(encoding="utf-8"))
        self.strict = strict

    @property
    def supported_markets(self) -> set[str]:
        return {str(value).upper() for value in self.data.get("supported_markets", [])}

    def evaluate(self, product: ProductRecord, market: str) -> PolicyDecision:
        market = market.strip().upper()
        if not market or market not in self.supported_markets:
            return PolicyDecision(
                False, "deny", ["unsupported_or_unspecified_market"], []
            )
        text = self._search_text(product)
        matches: list[str] = []
        reasons: list[str] = []
        deny_groups = dict(self.data.get("deny", {}))
        deny_groups.update(
            self.data.get("market_overrides", {}).get(market, {}).get("deny", {})
        )
        for group, terms in deny_groups.items():
            found = self._matches(text, terms)
            if found:
                matches.extend(found)
                reasons.append(f"deny:{group}")
        if reasons:
            return PolicyDecision(
                False, "deny", sorted(set(reasons)), sorted(set(matches))
            )

        review_reasons: list[str] = []
        review_groups = dict(self.data.get("review", {}))
        review_groups.update(
            self.data.get("market_overrides", {}).get(market, {}).get("review", {})
        )
        for group, terms in review_groups.items():
            found = self._matches(text, terms)
            if found:
                matches.extend(found)
                review_reasons.append(f"review:{group}")
        if review_reasons:
            return PolicyDecision(
                not self.strict,
                "review",
                sorted(set(review_reasons)),
                sorted(set(matches)),
            )
        return PolicyDecision(True, "allow", [], [])

    def _search_text(self, product: ProductRecord) -> str:
        parts: list[str] = [product.title, product.brand or ""]
        for category in product.categories:
            parts.extend(str(value) for value in category.values())
        parts.append(json.dumps(product.attributes, ensure_ascii=False, default=str))
        return " ".join(parts).casefold()

    @staticmethod
    def _matches(text: str, terms: list[Any]) -> list[str]:
        found: list[str] = []
        for term in terms:
            token = str(term).strip().casefold()
            if token and token in text:
                found.append(str(term))
        return found

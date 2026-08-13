from typing import Any

from app.config import Settings
from app.connectors.amazon import AmazonSPAPIClient


class DummyAsyncClient:
    async def aclose(self) -> None:
        return None


def _client() -> AmazonSPAPIClient:
    return AmazonSPAPIClient(Settings(app_mode="test"), client=DummyAsyncClient())  # type: ignore[arg-type]


def test_normalize_uses_landed_offer_price_and_ignores_points() -> None:
    client = _client()
    catalog: dict[str, Any] = {
        "summaries": [{"itemName": "Safe test product", "brand": "Example"}],
        "images": [],
    }
    pricing = {
        "responses": [
            {
                "body": {
                    "featuredBuyingOptions": [
                        {
                            "listingPrice": {"amount": 3980, "currencyCode": "JPY"},
                            "shippingOptions": [
                                {"price": {"amount": 500, "currencyCode": "JPY"}}
                            ],
                            "points": {
                                "pointsMonetaryValue": {
                                    "amount": 1,
                                    "currencyCode": "JPY",
                                }
                            },
                        }
                    ]
                }
            }
        ]
    }
    offers = {
        "payload": {
            "Offers": [
                {
                    "ListingPrice": {"Amount": 4200, "CurrencyCode": "JPY"},
                    "Shipping": {"Amount": 0, "CurrencyCode": "JPY"},
                    "LoyaltyPoints": {
                        "PointsMonetaryValue": {
                            "Amount": 1,
                            "CurrencyCode": "JPY",
                        }
                    },
                }
            ]
        }
    }

    product = client._normalize("B0TEST1234", catalog, pricing, offers)

    assert product.price == 4200
    assert product.currency == "JPY"
    assert product.available is True


def test_reference_price_without_offer_is_not_sellable() -> None:
    client = _client()
    catalog = {"summaries": [{"itemName": "Reference-only product"}], "images": []}
    pricing = {
        "responses": [
            {
                "body": {
                    "referencePrices": [
                        {
                            "name": "WasPrice",
                            "price": {"amount": 999, "currencyCode": "JPY"},
                        }
                    ]
                }
            }
        ]
    }
    offers = {"payload": {"Offers": [], "Summary": {"TotalOfferCount": 0}}}

    product = client._normalize("B0TEST5678", catalog, pricing, offers)

    assert product.price is None
    assert product.available is False

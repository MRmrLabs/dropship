import unittest

from app.domain import SupplierProduct
from app.meli_marketplace import build_attributes, remove_price_outliers


def product(**overrides):
    data = {
        "id": 1,
        "supplier_id": 1,
        "sku": "AI-1-1",
        "title": "Hub USB C 7 en 1",
        "brand": "Voltix",
        "category": "hubs",
        "cost": 150,
        "supplier_shipping": 50,
        "stock": 10,
        "warranty": "30 dias",
        "lead_time_days": 2,
        "image_url": "",
        "product_url": "https://example.com",
        "assets_authorized": True,
        "market_competition_price": 399,
        "competition_level": "medium",
    }
    data.update(overrides)
    return SupplierProduct(**data)


class MeliMarketplaceTests(unittest.TestCase):
    def test_build_attributes_includes_seller_sku(self):
        attrs = build_attributes({"attributes": {"brand": "Voltix"}}, product())
        ids = {item["id"]: item.get("value_name") or item.get("value_id") for item in attrs}
        self.assertEqual(ids["BRAND"], "Voltix")
        self.assertEqual(ids["ITEM_CONDITION"], "2230284")
        self.assertEqual(ids["SELLER_SKU"], "AI-1-1")

    def test_remove_price_outliers_drops_extreme_prices(self):
        items = [
            {"price": 10},
            {"price": 390},
            {"price": 410},
            {"price": 4500},
        ]
        cleaned = remove_price_outliers(items)
        self.assertEqual([item["price"] for item in cleaned], [390, 410])


if __name__ == "__main__":
    unittest.main()

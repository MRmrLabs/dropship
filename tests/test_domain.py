import unittest

from app.domain import (
    MIN_NET_MARGIN,
    Signal,
    Supplier,
    SupplierProduct,
    analyze_product,
    build_listing_draft,
    calculate_financials,
)


def supplier(**overrides):
    data = {
        "id": 1,
        "name": "Distribuidora MX",
        "country": "Mexico",
        "website": "https://example.com",
        "contact": "ventas@example.com",
        "terms": "Factura y garantia",
        "shipping_type": "Paqueteria",
        "reliability": 90,
        "invoices": True,
        "authorized_assets": True,
    }
    data.update(overrides)
    return Supplier(**data)


def product(**overrides):
    data = {
        "id": 10,
        "supplier_id": 1,
        "sku": "SKU-1",
        "title": "Cable USB-C Nylon",
        "brand": "Voltix",
        "category": "cables",
        "cost": 80,
        "supplier_shipping": 20,
        "stock": 20,
        "warranty": "30 dias",
        "lead_time_days": 1,
        "image_url": "https://example.com/img.jpg",
        "product_url": "https://example.com/p",
        "assets_authorized": True,
        "market_competition_price": 199,
        "competition_level": "medium",
    }
    data.update(overrides)
    return SupplierProduct(**data)


class DomainTests(unittest.TestCase):
    def test_margin_calculation_meets_minimum_when_price_is_suggested(self):
        financials = calculate_financials(product())
        self.assertGreaterEqual(financials["net_margin_rate"], MIN_NET_MARGIN)
        self.assertGreater(financials["net_profit"], 0)

    def test_good_accessory_is_green(self):
        opportunity = analyze_product(product(), supplier())
        self.assertEqual(opportunity.signal, Signal.GREEN)
        self.assertEqual(opportunity.risks, [])

    def test_low_stock_moves_to_review_or_red(self):
        opportunity = analyze_product(product(stock=2), supplier())
        self.assertIn("Stock bajo o incierto", opportunity.risks)
        self.assertNotEqual(opportunity.signal, Signal.GREEN)

    def test_risky_brand_requires_review(self):
        opportunity = analyze_product(product(brand="Apple"), supplier())
        self.assertIn("Marca con posible restriccion o garantia sensible", opportunity.risks)
        self.assertNotEqual(opportunity.signal, Signal.GREEN)

    def test_listing_draft_needs_review_for_non_green(self):
        risky = analyze_product(product(brand="Apple"), supplier())
        draft = build_listing_draft(product(brand="Apple"), risky)
        self.assertEqual(draft["status"], "needs_review")


if __name__ == "__main__":
    unittest.main()


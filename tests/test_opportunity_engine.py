import unittest

from app.domain import Supplier, SupplierProduct, analyze_product
from app.opportunity_engine import (
    build_opportunity_plan,
    evaluate_evidence,
    rank_opportunities,
    score_candidate,
)


def supplier(**overrides):
    data = {
        "id": 1,
        "name": "Mayorista MX",
        "country": "Mexico",
        "website": "https://mayorista.mx",
        "contact": "ventas@mayorista.mx",
        "terms": "Factura y garantia",
        "shipping_type": "Paqueteria",
        "reliability": 92,
        "invoices": True,
        "authorized_assets": True,
    }
    data.update(overrides)
    return Supplier(**data)


def product(**overrides):
    data = {
        "id": 10,
        "supplier_id": 1,
        "sku": "HUB-1",
        "title": "Hub USB-C 7 en 1",
        "brand": "Generico",
        "category": "hubs",
        "cost": 120,
        "supplier_shipping": 20,
        "stock": 20,
        "warranty": "30 dias",
        "lead_time_days": 1,
        "image_url": "",
        "product_url": "https://mayorista.mx/producto/hub-usb-c-7-en-1",
        "assets_authorized": True,
        "market_competition_price": 299,
        "competition_level": "low",
        "evidence_score": 0.9,
        "confidence_score": 0.9,
    }
    data.update(overrides)
    fields = SupplierProduct.__dataclass_fields__
    return SupplierProduct(**{key: value for key, value in data.items() if key in fields})


def evidence():
    return [
        {
            "evidence_type": "supplier_product_url",
            "url": "https://mayorista.mx/producto/hub-usb-c-7-en-1",
            "label": "Producto proveedor",
        },
        {
            "evidence_type": "marketplace_comparable_url",
            "url": "https://www.mercadolibre.com.mx/hub-usb-c-7-en-1/p/MLM123",
            "label": "Comparable marketplace",
        },
        {
            "evidence_type": "invoice_evidence",
            "url": "https://mayorista.mx/contacto",
            "label": "Factura/RFC/contacto",
        },
    ]


class OpportunityEngineTests(unittest.TestCase):
    def test_direct_evidence_beats_many_weak_urls(self):
        weak = evaluate_evidence(
            {
                "source_urls": [
                    "https://blog.example.com/accesorios",
                    "https://example.com/noticias/hubs",
                    "https://foro.example.com/post",
                ]
            }
        )
        strong = evaluate_evidence(
            {
                "supplier_product_url": "https://mayorista.mx/producto/hub-usb-c-7-en-1",
                "marketplace_comparable_url": "https://www.mercadolibre.com.mx/hub-usb-c/p/MLM123",
                "invoice_evidence": "https://mayorista.mx/contacto",
            }
        )
        self.assertGreater(strong["evidence_score"], weak["evidence_score"])

    def test_high_margin_low_demand_is_monitor(self):
        low_demand = product(
            category="micas",
            cost=30,
            market_competition_price=199,
            competition_level="high",
            title="Mica generica para tablet vieja",
        )
        plan = build_opportunity_plan(low_demand, supplier(), analyze_product(low_demand, supplier()), evidence())
        self.assertEqual(plan.recommendation, "monitor")

    def test_medium_margin_strong_evidence_low_competition_is_recommended(self):
        candidate = product(cost=100, market_competition_price=399, competition_level="low")
        plan = build_opportunity_plan(candidate, supplier(), analyze_product(candidate, supplier()), evidence())
        self.assertEqual(plan.recommendation, "buy_test")
        self.assertGreater(plan.expected_profit_adjusted, 0)

    def test_risky_brand_never_becomes_buy_test(self):
        risky = product(brand="Apple", title="Cable Apple Lightning", competition_level="low")
        plan = build_opportunity_plan(risky, supplier(), analyze_product(risky, supplier()), evidence())
        self.assertNotEqual(plan.recommendation, "buy_test")

    def test_missing_marketplace_comparable_needs_validation(self):
        sparse_evidence = [
            {
                "evidence_type": "supplier_product_url",
                "url": "https://mayorista.mx/producto/hub-usb-c-7-en-1",
                "label": "Producto proveedor",
            }
        ]
        candidate = product(cost=100, market_competition_price=399, competition_level="low")
        plan = build_opportunity_plan(candidate, supplier(), analyze_product(candidate, supplier()), sparse_evidence)
        self.assertEqual(plan.recommendation, "validate_supplier")

    def test_ranking_uses_adjusted_value_not_margin_only(self):
        stable = build_opportunity_plan(
            product(cost=125, market_competition_price=299, competition_level="low"),
            supplier(),
            None,
            evidence(),
        )
        high_margin_risky = build_opportunity_plan(
            product(
                cost=35,
                market_competition_price=299,
                competition_level="high",
                stock=2,
                assets_authorized=False,
                evidence_score=0.2,
                confidence_score=0.2,
            ),
            supplier(reliability=55, invoices=False, authorized_assets=False),
            None,
            evidence(),
        )
        ranked = rank_opportunities([high_margin_risky, stable])
        self.assertEqual(ranked[0]["product_id"], stable.product_id)

    def test_plan_always_has_action_evidence_and_summary(self):
        candidate = product()
        plan = build_opportunity_plan(candidate, supplier(), analyze_product(candidate, supplier()), evidence())
        self.assertTrue(plan.action_steps)
        self.assertTrue(plan.evidence_urls)
        self.assertTrue(plan.decision_summary)

    def test_market_price_snapshot_change_reduces_adjusted_profit(self):
        before = product(cost=120, market_competition_price=299)
        after = product(cost=120, market_competition_price=220)
        before_plan = build_opportunity_plan(before, supplier(), analyze_product(before, supplier()), evidence())
        after_plan = build_opportunity_plan(after, supplier(), analyze_product(after, supplier()), evidence())
        self.assertLess(after_plan.expected_profit_adjusted, before_plan.expected_profit_adjusted)

    def test_score_candidate_returns_operational_plan_fields(self):
        result = score_candidate(
            {
                "supplier_name": "Mayorista MX",
                "supplier_website": "https://mayorista.mx",
                "supplier_contact": "ventas@mayorista.mx",
                "product_title": "Hub USB-C 7 en 1",
                "brand": "Generico",
                "category": "hubs",
                "estimated_cost_mxn": 120,
                "estimated_shipping_mxn": 20,
                "estimated_market_price_mxn": 299,
                "suggested_sale_price_mxn": 299,
                "stock_signal": "alto",
                "warranty": "30 dias",
                "lead_time_days": 1,
                "supplier_product_url": "https://mayorista.mx/producto/hub-usb-c-7-en-1",
                "marketplace_comparable_url": "https://www.mercadolibre.com.mx/hub-usb-c/p/MLM123",
                "invoice_evidence": "https://mayorista.mx/contacto",
                "stock_evidence": "https://mayorista.mx/producto/hub-usb-c-7-en-1",
                "buyer_reason": "Resuelve conectividad para laptops modernas con pocos puertos.",
                "field_verifiability": "alto",
                "source_urls": [],
                "risk_flags": [],
                "confidence": 0.86,
                "notes": "Validar precio final",
            }
        )
        self.assertIn(result["recommendation"], {"buy_test", "validate_supplier", "monitor", "reject"})
        self.assertIn("expected_profit_adjusted", result)
        self.assertTrue(result["evidence_items"])


if __name__ == "__main__":
    unittest.main()

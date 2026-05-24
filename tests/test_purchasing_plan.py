import unittest

from app.purchasing_plan import MIN_PURCHASE_CONFIDENCE, build_purchase_plan


def opportunity(**overrides):
    evidence_total = overrides.pop("evidence_total", 90)
    data = {
        "product_id": 1,
        "platform": "mercado_libre_mx",
        "sku": "SKU-1",
        "title": "Hub USB-C 7 en 1",
        "brand": "Generico",
        "category": "hubs",
        "stock": 20,
        "cost": 220,
        "supplier_shipping": 0,
        "warranty": "30 dias",
        "lead_time_days": 1,
        "image_url": "",
        "product_url": "https://mayorista.mx/producto/hub-usb-c",
        "assets_authorized": True,
        "market_competition_price": 399,
        "competition_level": "low",
        "source_type": "ai",
        "supplier_id": 1,
        "supplier_name": "Mayorista MX",
        "supplier_country": "Mexico",
        "supplier_website": "https://mayorista.mx",
        "supplier_contact": "ventas@mayorista.mx",
        "supplier_terms": "Factura y garantia",
        "supplier_shipping_type": "Paqueteria",
        "supplier_reliability": 95,
        "supplier_invoices": True,
        "supplier_authorized_assets": True,
        "suggested_price": 399,
        "net_margin_rate": 0.30,
        "net_profit": 120,
        "score": 88,
        "signal": "green",
        "risks": [],
        "intelligence": {
            "potential_score": 88,
            "verdict": "Recomendada",
            "verdict_signal": "green",
            "saturation": "Baja",
            "competition": "Baja",
            "return_risk": "Bajo",
            "visual_potential": "Alto",
            "alerts": [],
            "financials": {},
        },
    }
    if evidence_total is not None:
        data["evidence"] = {"score_details": {"total": evidence_total}}
    data.update(overrides)
    return data


class PurchasingPlanTests(unittest.TestCase):
    def test_budget_distributes_across_multiple_good_opportunities(self):
        plan = build_purchase_plan(
            5000,
            [
                opportunity(product_id=1, title="Hub USB-C 7 en 1"),
                opportunity(product_id=2, title="Soporte laptop aluminio", category="soportes", cost=260, net_profit=105),
            ],
        )
        self.assertGreaterEqual(len(plan["items"]), 2)
        self.assertGreater(plan["allocated_mxn"], 0)
        self.assertLessEqual(plan["allocated_mxn"], 5000)
        self.assertGreaterEqual(plan["confidence"], MIN_PURCHASE_CONFIDENCE)

    def test_single_good_opportunity_uses_part_and_reserves_leftover(self):
        plan = build_purchase_plan(
            5000,
            [
                opportunity(product_id=1),
                opportunity(
                    product_id=2,
                    title="Cable marca sensible",
                    score=45,
                    evidence_total=40,
                    net_margin_rate=0.16,
                    signal="yellow",
                    risks=["Marca con posible restriccion o garantia sensible"],
                ),
            ],
        )
        self.assertEqual(len(plan["items"]), 1)
        self.assertGreater(plan["reserved_mxn"], 0)
        self.assertEqual(plan["verdict"], "Invertir parcial")

    def test_low_confidence_opportunities_do_not_receive_capital(self):
        plan = build_purchase_plan(
            2000,
            [
                opportunity(
                    score=50,
                    evidence_total=45,
                    net_margin_rate=0.16,
                    supplier_reliability=65,
                    signal="yellow",
                )
            ],
        )
        self.assertEqual(plan["allocated_mxn"], 0)
        self.assertEqual(plan["items"], [])
        self.assertIn("80%", plan["summary"])

    def test_high_roi_high_risk_does_not_beat_lower_roi_strong_evidence(self):
        plan = build_purchase_plan(
            2500,
            [
                opportunity(product_id=1, title="Adaptador estable", cost=240, net_profit=85, net_margin_rate=0.24),
                opportunity(
                    product_id=2,
                    title="Cable Apple riesgoso",
                    brand="Apple",
                    cost=45,
                    net_profit=180,
                    net_margin_rate=0.55,
                    score=95,
                    evidence_total=95,
                    signal="yellow",
                    supplier_invoices=False,
                    assets_authorized=False,
                    supplier_authorized_assets=False,
                    risks=["Marca con posible restriccion o garantia sensible", "Imagenes/textos sin autorizacion confirmada"],
                ),
            ],
        )
        self.assertEqual(plan["items"][0]["product_id"], 1)
        rejected_ids = {item["product_id"] for item in plan["rejected_or_reserved"]}
        self.assertIn(2, rejected_ids)

    def test_quantity_never_exceeds_stock_or_budget(self):
        low_stock = build_purchase_plan(5000, [opportunity(stock=2)])
        self.assertLessEqual(low_stock["items"][0]["quantity"], 2)

        low_budget = build_purchase_plan(450, [opportunity(stock=20)])
        self.assertLessEqual(low_budget["items"][0]["total_investment"], 450)
        self.assertEqual(low_budget["items"][0]["quantity"], 2)

    def test_plan_includes_required_totals_and_items(self):
        plan = build_purchase_plan(1200, [opportunity()])
        for key in ["allocated_mxn", "reserved_mxn", "expected_profit_mxn", "confidence", "items"]:
            self.assertIn(key, plan)
        self.assertTrue(plan["items"])
        self.assertIn("steps", plan["items"][0])

    def test_no_good_opportunities_returns_zero_allocation_with_reason(self):
        plan = build_purchase_plan(
            3000,
            [
                opportunity(
                    score=30,
                    evidence_total=20,
                    net_margin_rate=0.08,
                    net_profit=5,
                    signal="red",
                    risks=["Margen neto menor a 15%", "Stock bajo o incierto"],
                )
            ],
        )
        self.assertEqual(plan["allocated_mxn"], 0)
        self.assertEqual(plan["reserved_mxn"], 3000)
        self.assertIn("No recomiendo invertir", plan["summary"])

    def test_budget_changes_quantities_without_changing_risk_rules(self):
        strong = opportunity(
            score=98,
            evidence_total=98,
            supplier_reliability=99,
            net_margin_rate=0.45,
            net_profit=150,
            stock=20,
            cost=200,
        )
        small = build_purchase_plan(450, [strong])
        large = build_purchase_plan(1100, [strong])
        self.assertEqual(small["items"][0]["quantity"], 2)
        self.assertEqual(large["items"][0]["quantity"], 5)
        self.assertGreaterEqual(small["items"][0]["confidence"], MIN_PURCHASE_CONFIDENCE)
        self.assertGreaterEqual(large["items"][0]["confidence"], MIN_PURCHASE_CONFIDENCE)


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch

from app.deep_search import DeepSearchEngine, OpportunityVerifier, is_source_error_reason, score_candidate


def candidate(index=1, **overrides):
    data = {
        "supplier_name": f"Proveedor {index}",
        "supplier_website": f"https://proveedor{index}.mx",
        "supplier_contact": "ventas@proveedor.mx factura RFC",
        "product_title": f"Hub USB C 7 en 1 modelo rentable {index}",
        "brand": "Generico",
        "category": "hubs",
        "estimated_cost_mxn": 120,
        "estimated_shipping_mxn": 35,
        "estimated_market_price_mxn": 399,
        "suggested_sale_price_mxn": 449,
        "stock_signal": "alto",
        "warranty": "30 dias",
        "lead_time_days": 2,
        "source_urls": [f"https://proveedor{index}.mx/p/{index}"],
        "supplier_buy_url": f"https://proveedor{index}.mx/p/{index}",
        "meli_reference_urls": ["https://listado.mercadolibre.com.mx/hub-usb-c"],
        "competition_count_estimate": 22,
        "saturation_signal": "baja",
        "demand_signal": "alta",
        "why_it_can_sell": "Producto util y visual",
        "investment_plan": "Pide 3, valida stock y factura",
        "risk_flags": [],
        "confidence": 0.86,
        "notes": "disponible con factura",
    }
    data.update(overrides)
    return data


def market(_query, _reference):
    return {
        "query": _query,
        "count": 18,
        "reference_price": 429,
        "median_price": 429,
        "min_price": 379,
        "seller_count": 5,
        "full_shipping_count": 2,
        "competition_level": "low",
        "items": [],
    }


class DeepSearchTests(unittest.TestCase):
    @patch("app.deep_search.insert_market_snapshot", lambda *args, **kwargs: 1)
    @patch("app.deep_search.insert_supplier_snapshot", lambda *args, **kwargs: 1)
    @patch("app.deep_search.insert_trend_snapshot", lambda *args, **kwargs: 1)
    @patch("app.deep_search.insert_rejected_candidate", lambda *args, **kwargs: 1)
    @patch("app.deep_search.is_recently_rejected", lambda *args, **kwargs: False)
    @patch.dict("os.environ", {"AI_REQUIRED_CANDIDATES": "4", "AI_RESEARCH_MAX_ATTEMPTS": "2"}, clear=False)
    def test_deep_search_returns_exactly_four_winners(self):
        def fake_research(_api_key, _prompt):
            return {"summary": "ok", "candidates": [candidate(i) for i in range(1, 6)]}, {"id": "resp_1"}

        engine = DeepSearchEngine(
            research_request=fake_research,
            market_compare=market,
            trends_fetcher=lambda _category: {"items": [{"keyword": "hub usb c"}]},
            provider_verify=lambda _url: {"available": True, "reason": "ok", "has_buy_signal": True, "price_visible": 120},
        )
        result = engine.run("hubs usb c")
        self.assertEqual(result["engine"], "primeloot_deep_search_v2")
        self.assertEqual(len(result["candidates"]), 4)
        self.assertEqual(result["candidates"][0]["score_details"]["signal"], "elite")

    @patch("app.deep_search.is_recently_rejected", lambda *args, **kwargs: False)
    def test_verifier_rejects_bad_availability(self):
        verifier = OpportunityVerifier(market, lambda _url: {"available": True, "reason": "ok"})
        result = verifier.verify(candidate(notes="agotado temporalmente"))
        self.assertFalse(result.accepted)
        self.assertIn("Disponibilidad", result.reason)

    @patch("app.deep_search.is_recently_rejected", lambda *args, **kwargs: False)
    def test_verifier_classifies_404_as_source_error_not_product_rejection(self):
        verifier = OpportunityVerifier(
            market,
            lambda _url: {
                "available": False,
                "reason": "No se pudo abrir proveedor: HTTP 404",
                "failure_kind": "http_404",
                "root_available": True,
            },
        )
        result = verifier.verify(candidate())
        self.assertFalse(result.accepted)
        self.assertIn("URL directa de proveedor rota", result.reason)
        self.assertTrue(is_source_error_reason(result.reason))

    def test_score_candidate_has_subscores(self):
        score = score_candidate(candidate(), market("hub", 399))
        self.assertGreaterEqual(score["total"], 70)
        self.assertIn("demanda", score["subscores"])
        self.assertIn("competencia", score["subscores"])


if __name__ == "__main__":
    unittest.main()

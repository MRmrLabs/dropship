import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.ai_research import enforce_usage_limits, parse_json_object, research_schema, valid_candidates


class AiResearchTests(unittest.TestCase):
    def test_parse_json_object_plain(self):
        parsed = parse_json_object('{"summary":"ok","candidates":[]}')
        self.assertEqual(parsed["summary"], "ok")

    def test_parse_json_object_from_markdown_block(self):
        parsed = parse_json_object('```json\n{"summary":"ok","candidates":[]}\n```')
        self.assertEqual(parsed["candidates"], [])

    def test_parse_json_object_repairs_trailing_commas(self):
        parsed = parse_json_object('{"summary":"ok","candidates":[{"product_title":"Cable",}],}')
        self.assertEqual(parsed["candidates"][0]["product_title"], "Cable")

    def test_research_schema_requires_candidates(self):
        schema = research_schema()
        self.assertIn("candidates", schema["required"])
        self.assertTrue(schema["additionalProperties"] is False)
        candidate_schema = schema["properties"]["candidates"]["items"]["properties"]
        self.assertEqual(candidate_schema["estimated_cost_mxn"]["minimum"], 20)

    def test_valid_candidates_removes_placeholder_prices(self):
        candidates = [
            {
                "supplier_name": "Proveedor MX",
                "product_title": "Hub USB C 7 en 1 marca real",
                "estimated_cost_mxn": 100,
                "estimated_shipping_mxn": 50,
                "estimated_market_price_mxn": 1,
                "suggested_sale_price_mxn": 1,
                "source_urls": ["https://example.com/producto"],
            },
            {
                "supplier_name": "Proveedor MX",
                "product_title": "Soporte laptop aluminio modelo real",
                "estimated_cost_mxn": 120,
                "estimated_shipping_mxn": 40,
                "estimated_market_price_mxn": 299,
                "suggested_sale_price_mxn": 329,
                "source_urls": ["https://example.com/soporte"],
            },
        ]
        self.assertEqual(len(valid_candidates(candidates)), 1)

    @patch.dict("os.environ", {"AI_DAILY_SEARCH_LIMIT": "3"}, clear=False)
    def test_daily_limit_blocks_extra_searches(self):
        with self.assertRaisesRegex(ValueError, "Limite diario"):
            enforce_usage_limits(3, None)

    @patch.dict("os.environ", {"AI_MIN_SECONDS_BETWEEN_SEARCHES": "300"}, clear=False)
    def test_min_interval_blocks_fast_repeat(self):
        latest = datetime.now(timezone.utc) - timedelta(seconds=30)
        with self.assertRaisesRegex(ValueError, "Espera"):
            enforce_usage_limits(0, {"created_at": latest.strftime("%Y-%m-%d %H:%M:%S")})


if __name__ == "__main__":
    unittest.main()

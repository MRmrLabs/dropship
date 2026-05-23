import unittest

from app.provider_verifier import extract_price, html_to_text, verify_provider_page


class ProviderVerifierTests(unittest.TestCase):
    def test_extract_price_from_page_text(self):
        self.assertEqual(extract_price("Precio especial $249.00 MXN"), 249.0)

    def test_html_to_text_removes_tags(self):
        self.assertEqual(html_to_text("<h1>Hub</h1><script>x</script><p>Comprar ahora</p>"), "Hub Comprar ahora")

    def test_invalid_url_is_not_available(self):
        result = verify_provider_page("not-a-url")
        self.assertFalse(result["available"])
        self.assertIn("invalida", result["reason"])


if __name__ == "__main__":
    unittest.main()

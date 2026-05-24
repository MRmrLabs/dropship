import unittest
from urllib.error import HTTPError
from unittest.mock import patch

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
        self.assertEqual(result["failure_kind"], "invalid_url")

    def test_404_marks_broken_product_url_and_checks_root(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b"<html><body>Contacto RFC factura cotizar</body></html>"

        def fake_urlopen(request, timeout):
            url = request.full_url
            if url.endswith("/products/slug-inventado"):
                raise HTTPError(url, 404, "Not Found", None, None)
            return FakeResponse()

        with patch("app.provider_verifier.urlopen", fake_urlopen):
            result = verify_provider_page("https://proveedor.mx/products/slug-inventado")

        self.assertFalse(result["available"])
        self.assertEqual(result["failure_kind"], "http_404")
        self.assertEqual(result["status_code"], 404)
        self.assertTrue(result["root_available"])
        self.assertEqual(result["root_url"], "https://proveedor.mx")


if __name__ == "__main__":
    unittest.main()

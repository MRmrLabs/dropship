import hmac
import json
import os
import time
import unittest
from hashlib import sha256

from app.auth import is_authenticated, login_cookie, verify_password
from app.reports import build_investment_plan, plan_to_pdf_bytes
from app.stripe_payments import verify_webhook_signature


class PremiumFeatureTests(unittest.TestCase):
    def test_auth_cookie_validates_admin_session(self):
        old_password = os.environ.get("ADMIN_PASSWORD")
        old_secret = os.environ.get("ADMIN_SESSION_SECRET")
        try:
            os.environ["ADMIN_PASSWORD"] = "secret"
            os.environ["ADMIN_SESSION_SECRET"] = "session-secret"
            self.assertTrue(verify_password("secret"))
            self.assertTrue(is_authenticated(login_cookie()))
        finally:
            restore_env("ADMIN_PASSWORD", old_password)
            restore_env("ADMIN_SESSION_SECRET", old_secret)

    def test_investment_plan_has_actionable_numbers(self):
        item = {
            "product_id": 10,
            "title": "Hub USB-C 7 en 1",
            "sku": "HUB-7",
            "supplier_name": "Proveedor MX",
            "product_url": "https://example.com/hub",
            "cost": 180,
            "supplier_shipping": 80,
            "stock": 8,
            "suggested_price": 499,
            "net_profit": 95,
            "net_margin_rate": 0.24,
            "lead_time_days": 2,
            "score": 78,
            "risks": [],
            "intelligence": {"potential_score": 82, "verdict": "Recomendada"},
        }
        plan = build_investment_plan(item)
        self.assertEqual(plan["quantity"], 3)
        self.assertGreater(plan["total_investment"], 0)
        self.assertIn("Comprar", " ".join(plan["steps"]))
        self.assertTrue(plan_to_pdf_bytes(plan).startswith(b"%PDF"))

    def test_stripe_signature_validation(self):
        old_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
        try:
            os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test"
            payload = json.dumps({"type": "checkout.session.completed"}).encode("utf-8")
            timestamp = str(int(time.time()))
            signed = f"{timestamp}.".encode("utf-8") + payload
            digest = hmac.new(b"whsec_test", signed, sha256).hexdigest()
            self.assertTrue(verify_webhook_signature(payload, f"t={timestamp},v1={digest}"))
            self.assertFalse(verify_webhook_signature(payload, f"t={timestamp},v1=bad"))
        finally:
            restore_env("STRIPE_WEBHOOK_SECRET", old_secret)


def restore_env(key, value):
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()

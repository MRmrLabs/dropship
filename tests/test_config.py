import os
import unittest

from app.config import get_meli_config


class ConfigTests(unittest.TestCase):
    def test_meli_config_reads_environment(self):
        old = {
            "MELI_CLIENT_ID": os.environ.get("MELI_CLIENT_ID"),
            "MELI_CLIENT_SECRET": os.environ.get("MELI_CLIENT_SECRET"),
            "MELI_REDIRECT_URI": os.environ.get("MELI_REDIRECT_URI"),
        }
        try:
            os.environ["MELI_CLIENT_ID"] = "123"
            os.environ["MELI_CLIENT_SECRET"] = "secret"
            os.environ["MELI_REDIRECT_URI"] = "http://127.0.0.1:8787/auth/meli/callback"
            config = get_meli_config()
            self.assertTrue(config.is_complete)
            self.assertEqual(config.client_id, "123")
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()

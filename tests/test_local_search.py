import unittest
from unittest.mock import patch

from app.local_search import get_local_search_job, local_search_status, run_local_search_job, start_local_search, stop_local_search_job


class LocalSearchTests(unittest.TestCase):
    @patch.dict("os.environ", {"LOCAL_SEARCH_ENABLED": "true", "LOCAL_SUPPLIER_URLS": ""}, clear=False)
    def test_local_search_status_reads_env(self):
        status = local_search_status()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["profile"], "balanced")

    @patch.dict("os.environ", {"LOCAL_SEARCH_ENABLED": "true", "LOCAL_SUPPLIER_URLS": ""}, clear=False)
    @patch("app.local_search.threading.Thread.start", lambda _self: None)
    def test_local_search_job_can_start_and_stop(self):
        job = start_local_search("hubs usb")
        self.assertIn(job["status"], {"queued", "running", "completed", "failed"})
        stopped = stop_local_search_job(job["id"])
        self.assertTrue(get_local_search_job(stopped["id"]))

    @patch.dict("os.environ", {"LOCAL_SEARCH_ENABLED": "true", "LOCAL_SUPPLIER_URLS": "", "OPENAI_API_KEY": "sk-test"}, clear=False)
    @patch("app.local_search.threading.Thread.start", lambda _self: None)
    @patch("app.local_search.fetch_trends", lambda _category: {"items": []})
    @patch("app.local_search.deep_search_products", side_effect=ValueError("OpenAI Web Search respondio 403 Forbidden"))
    def test_local_search_fails_actionably_when_openai_forbidden_and_no_seeds(self, _mock_deep):
        job = start_local_search("hubs usb")
        run_local_search_job(job["id"])
        final = get_local_search_job(job["id"])
        self.assertEqual(final["status"], "failed")
        self.assertIn("LOCAL_SUPPLIER_URLS", final["error"])


if __name__ == "__main__":
    unittest.main()

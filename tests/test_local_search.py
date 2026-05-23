import unittest
from unittest.mock import patch

from app.local_search import get_local_search_job, local_search_status, start_local_search, stop_local_search_job


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


if __name__ == "__main__":
    unittest.main()

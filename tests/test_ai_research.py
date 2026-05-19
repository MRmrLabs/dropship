import unittest

from app.ai_research import parse_json_object


class AiResearchTests(unittest.TestCase):
    def test_parse_json_object_plain(self):
        parsed = parse_json_object('{"summary":"ok","candidates":[]}')
        self.assertEqual(parsed["summary"], "ok")

    def test_parse_json_object_from_markdown_block(self):
        parsed = parse_json_object('```json\n{"summary":"ok","candidates":[]}\n```')
        self.assertEqual(parsed["candidates"], [])


if __name__ == "__main__":
    unittest.main()

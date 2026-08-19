import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from source_scout.gemini_video import GeminiVideoError, analyze_video


class GeminiVideoTests(unittest.TestCase):
    def test_requires_api_key(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {}, clear=True):
            path = Path(directory) / "clip.mp4"
            path.write_bytes(b"video")
            with self.assertRaises(GeminiVideoError):
                analyze_video(path)

    @patch("source_scout.gemini_video.urlopen")
    def test_parses_structured_idea_response(self, urlopen):
        result = {
            "summary": "복원 영상",
            "timeline": [],
            "interesting_points": ["전후 차이"],
            "ideas": [
                {"title": "아이디어 1"}, {"title": "아이디어 2"}, {"title": "아이디어 3"},
            ],
            "research_needed": [],
        }
        response = MagicMock()
        response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": json.dumps(result, ensure_ascii=False)}]}}]
        }).encode()
        urlopen.return_value.__enter__.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            path.write_bytes(b"video")
            parsed = analyze_video(path, api_key="test-key")
        self.assertEqual(parsed["summary"], "복원 영상")
        self.assertEqual(len(parsed["ideas"]), 3)
        request = urlopen.call_args.args[0]
        self.assertNotIn("test-key", request.full_url)
        self.assertEqual(request.headers["X-goog-api-key"], "test-key")


if __name__ == "__main__":
    unittest.main()

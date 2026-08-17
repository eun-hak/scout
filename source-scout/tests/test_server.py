import unittest

from source_scout.analyzer import analyze_metadata
from source_scout.server import detect_platform, validate_url


class ServerTests(unittest.TestCase):
    def test_detects_supported_platforms(self):
        self.assertEqual(detect_platform("https://www.instagram.com/reel/abc"), "instagram")
        self.assertEqual(detect_platform("https://youtu.be/abc"), "youtube")
        self.assertEqual(detect_platform("https://example.com/video"), "web")

    def test_rejects_non_http_url(self):
        with self.assertRaises(ValueError):
            validate_url("file:///tmp/video.mp4")

    def test_metadata_analysis_suggests_process_theme(self):
        result = analyze_metadata(
            "Amazing restoration process",
            "This skilled worker explains how the traditional repair method works.",
            "@craftsperson",
            "instagram",
        )
        self.assertEqual(result["theme"], "직업·공정")
        self.assertGreaterEqual(result["explainability_score"], 3)
        self.assertEqual(result["traceability_score"], 4)


if __name__ == "__main__":
    unittest.main()

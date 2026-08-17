import os
import unittest
from unittest.mock import patch

from source_scout.analysis_provider import analyze_candidate


class AnalysisProviderTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_local_fallback_is_labeled_metadata_only(self):
        candidate = {"id": 1, "url": "https://example.com", "platform": "web", "title": "A process", "creator": "Creator", "notes": "How this works", "thumbnail_url": ""}
        result = analyze_candidate(candidate)
        self.assertEqual(result["analysis_status"], "metadata_only")
        self.assertEqual(len(result["script_ideas"]), 3)


if __name__ == "__main__":
    unittest.main()

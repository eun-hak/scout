import unittest

from source_scout.scoring import calculate_score, clamp_rating


class ScoringTests(unittest.TestCase):
    def test_neutral_score_includes_risk_penalty(self):
        values = {field: 3 for field in (
            "hook_score", "explainability_score", "novelty_score",
            "editability_score", "traceability_score", "risk_score"
        )}
        self.assertEqual(calculate_score(values), 50.0)

    def test_best_safe_candidate_scores_100(self):
        values = {field: 5 for field in (
            "hook_score", "explainability_score", "novelty_score",
            "editability_score", "traceability_score"
        )}
        values["risk_score"] = 1
        self.assertEqual(calculate_score(values), 100.0)

    def test_rating_is_clamped(self):
        self.assertEqual(clamp_rating(9), 5)
        self.assertEqual(clamp_rating(-1), 1)
        self.assertEqual(clamp_rating("bad"), 3)


if __name__ == "__main__":
    unittest.main()


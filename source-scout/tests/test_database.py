import tempfile
import unittest
from pathlib import Path

from source_scout.database import Database


class DatabaseTests(unittest.TestCase):
    def test_candidate_can_be_found_by_url_for_duplicate_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.db")
            created = database.create_candidate({
                "url": "https://www.instagram.com/reel/example/",
                "platform": "instagram",
                "title": "Shared reel",
            })
            found = database.get_candidate_by_url(created["url"])
            self.assertEqual(found["id"], created["id"])
            self.assertIsNone(database.get_candidate_by_url("https://example.com/missing"))

    def test_mobile_token_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.db")
            created = database.create_mobile_token("iPhone", "hashed-token")
            self.assertTrue(database.validate_mobile_token("hashed-token"))
            self.assertTrue(database.revoke_mobile_token(created["id"]))
            self.assertFalse(database.validate_mobile_token("hashed-token"))

    def test_meta_connection_lifecycle_hides_tokens_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.db")
            saved = database.save_meta_connection({
                "user_access_token": "user-secret",
                "page_access_token": "page-secret",
                "page_id": "page-1",
                "page_name": "SocialScout",
                "ig_user_id": "ig-1",
                "ig_username": "socialscout",
                "scopes": "instagram_basic,pages_show_list",
            })
            self.assertNotIn("user_access_token", saved)
            self.assertEqual(saved["ig_username"], "socialscout")
            secret = database.get_meta_connection(include_tokens=True)
            self.assertEqual(secret["user_access_token"], "user-secret")
            deleted = database.delete_meta_connection()
            self.assertEqual(deleted["page_id"], "page-1")
            self.assertIsNone(database.get_meta_connection())


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch

from source_scout.meta_api import inspect_connection, search_hashtag


class MetaAPITests(unittest.TestCase):
    @patch("source_scout.meta_api.graph_get")
    def test_inspect_connection_selects_page_with_instagram_account(self, graph_get):
        graph_get.return_value = {"data": [
            {"id": "page-a", "name": "No Instagram", "access_token": "a"},
            {"id": "page-b", "name": "SocialScout", "access_token": "b", "instagram_business_account": {"id": "ig-1", "username": "scout"}},
        ]}
        result = inspect_connection("user-token")
        self.assertEqual(result["page_id"], "page-b")
        self.assertEqual(result["ig_username"], "scout")

    @patch("source_scout.meta_api.graph_get")
    def test_hashtag_search_returns_limited_public_metadata(self, graph_get):
        graph_get.side_effect = [
            {"data": [{"id": "tag-1"}]},
            {"data": [{"id": "media-1", "permalink": "https://www.instagram.com/reel/abc/", "caption": "Craft", "media_type": "VIDEO", "username": "maker"}]},
        ]
        items = search_hashtag({"user_access_token": "token", "ig_user_id": "ig-1"}, "craft")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["username"], "maker")
        self.assertEqual(items[0]["permalink"], "https://www.instagram.com/reel/abc/")


if __name__ == "__main__":
    unittest.main()

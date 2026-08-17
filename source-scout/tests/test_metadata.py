import unittest

from source_scout.metadata import MetadataParser, canonicalize_url, ensure_public_url


class MetadataTests(unittest.TestCase):
    def test_canonicalize_removes_tracking_and_fragment(self):
        value = canonicalize_url("HTTPS://Example.COM/video/?utm_source=x&keep=1#part")
        self.assertEqual(value, "https://example.com/video?keep=1")

    def test_parser_prefers_open_graph_metadata(self):
        parser = MetadataParser()
        parser.feed('<html><head><title>Fallback</title><meta property="og:title" content="Clip"><meta property="og:image" content="https://img.example/a.jpg"></head></html>')
        result = parser.result()
        self.assertEqual(result["title"], "Clip")
        self.assertEqual(result["thumbnail_url"], "https://img.example/a.jpg")

    def test_private_address_is_rejected(self):
        with self.assertRaises(ValueError):
            ensure_public_url("http://127.0.0.1/private")


if __name__ == "__main__":
    unittest.main()

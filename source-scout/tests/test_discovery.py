import unittest

from source_scout.discovery import parse_feed


class DiscoveryTests(unittest.TestCase):
    def test_parse_rss(self):
        data = b'<?xml version="1.0"?><rss><channel><item><title>Clip</title><link>https://example.com/clip</link><description>Process</description></item></channel></rss>'
        entries = parse_feed(data)
        self.assertEqual(entries[0]["title"], "Clip")
        self.assertEqual(entries[0]["url"], "https://example.com/clip")

    def test_parse_atom(self):
        data = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Video</title><link href="https://example.com/video"/><summary>Summary</summary><author><name>Creator</name></author></entry></feed>'
        entries = parse_feed(data)
        self.assertEqual(entries[0]["creator"], "Creator")


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from source_scout.video_downloader import VideoDownloadError, download_video


class FakeDownloader:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def extract_info(self, url, download):
        self.url = url
        path = Path(self.options["outtmpl"].replace("%(id)s", "abc").replace("%(ext)s", "mp4"))
        path.write_bytes(b"video")
        self.path = path
        return {"id": "abc", "ext": "mp4", "title": "테스트 영상"}

    def prepare_filename(self, info):
        return str(self.path)


class FakeYTDLP:
    YoutubeDL = FakeDownloader


class VideoDownloaderTests(unittest.TestCase):
    def test_rejects_unrecognized_hosts(self):
        with self.assertRaises(VideoDownloadError):
            download_video("https://example.com/video", Path("unused"), 1, 100)

    def test_downloads_supported_video(self):
        with tempfile.TemporaryDirectory() as temporary, patch("source_scout.video_downloader.yt_dlp", FakeYTDLP):
            result = download_video("https://www.instagram.com/reel/abc", Path(temporary), 7, 100)
        self.assertEqual(result["size"], 5)
        self.assertTrue(str(result["path"]).endswith("candidate-7-abc.mp4"))


if __name__ == "__main__":
    unittest.main()

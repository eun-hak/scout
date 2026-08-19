import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from source_scout.tts_client import generate_tts


class FakeClient:
    calls = []

    def __init__(self, url, auth):
        self.url, self.auth = url, auth

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["api_name"] == "/do_gen_all":
            return [self.audio_path]
        return "split"


class TTSClientTests(unittest.TestCase):
    def test_generates_and_copies_audio(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "generated.wav"
            with wave.open(str(source), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(24000)
                audio.writeframes(b"\0\0" * 24000)
            FakeClient.audio_path = str(source)
            FakeClient.calls = []
            environment = {
                "SOURCE_SCOUT_TTS_URL": "https://tts.example.test",
                "SOURCE_SCOUT_TTS_USERNAME": "user",
                "SOURCE_SCOUT_TTS_PASSWORD": "password",
                "SOURCE_SCOUT_TTS_VOICE": "목소리1",
                "SOURCE_SCOUT_TTS_LANGUAGE": "Auto",
            }
            with patch.dict(os.environ, environment, clear=False), patch("source_scout.tts_client.Client", FakeClient):
                result = generate_tts("첫 문장입니다.", root / "output")
            self.assertEqual(result[0]["filename"], "sentence-01.wav")
            self.assertEqual(result[0]["duration_seconds"], 1.0)
            self.assertTrue((root / "output" / "sentence-01.wav").is_file())
            self.assertEqual(FakeClient.calls[0]["api_name"], "/do_split")
            self.assertEqual(FakeClient.calls[1]["voice"], "목소리1")


if __name__ == "__main__":
    unittest.main()

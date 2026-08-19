from __future__ import annotations

import os
import shutil
import wave
from pathlib import Path

try:
    from gradio_client import Client
except ImportError:  # pragma: no cover - handled with a user-facing error
    Client = None


class TTSError(RuntimeError):
    pass


def _paths(value: object) -> list[Path]:
    found: list[Path] = []
    if isinstance(value, (str, Path)):
        path = Path(value)
        if path.suffix.lower() in {".wav", ".mp3", ".flac", ".ogg"} and path.is_file():
            found.append(path)
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_paths(item))
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(_paths(item))
    return found


def _wav_duration(path: Path) -> float | None:
    if path.suffix.lower() != ".wav":
        return None
    try:
        with wave.open(str(path), "rb") as audio:
            return round(audio.getnframes() / audio.getframerate(), 2)
    except (wave.Error, OSError, ZeroDivisionError):
        return None


def generate_tts(script: str, output_dir: Path) -> list[dict]:
    url = os.environ.get("SOURCE_SCOUT_TTS_URL", "").strip().rstrip("/")
    username = os.environ.get("SOURCE_SCOUT_TTS_USERNAME", "").strip()
    password = os.environ.get("SOURCE_SCOUT_TTS_PASSWORD", "")
    voice = os.environ.get("SOURCE_SCOUT_TTS_VOICE", "목소리1").strip() or "목소리1"
    language = os.environ.get("SOURCE_SCOUT_TTS_LANGUAGE", "Auto").strip() or "Auto"
    if not url or not username or not password:
        raise TTSError("TTS 서버 주소와 로그인 정보가 설정되지 않았습니다.")
    if Client is None:
        raise TTSError("서버에 gradio_client 패키지가 설치되지 않았습니다.")

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        client = Client(url, auth=(username, password))
        client.predict(script=script, api_name="/do_split")
        result = client.predict(
            source="저장된 목소리", lang=language, voice=voice, speaker="Sohee",
            instruct=None, temp=0.55, sub=0.6, api_name="/do_gen_all",
        )
    except Exception as exc:
        raise TTSError(f"TTS 서버 생성 요청에 실패했습니다: {exc}") from exc

    source_files = _paths(result)
    if not source_files:
        raise TTSError("TTS 서버가 생성된 음성 파일을 반환하지 않았습니다.")
    files = []
    for index, source in enumerate(source_files, 1):
        suffix = source.suffix.lower() if source.suffix else ".wav"
        destination = output_dir / f"sentence-{index:02d}{suffix}"
        shutil.copy2(source, destination)
        files.append({
            "filename": destination.name,
            "duration_seconds": _wav_duration(destination),
            "mime_type": {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg"}.get(suffix, "audio/flac"),
        })
    return files

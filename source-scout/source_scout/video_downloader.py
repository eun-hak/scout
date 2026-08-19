from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

try:
    import yt_dlp
except ImportError:  # pragma: no cover
    yt_dlp = None


class VideoDownloadError(RuntimeError):
    pass


SUPPORTED_HOSTS = (
    "instagram.com", "tiktok.com", "youtube.com", "youtu.be",
)


def _supported_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in SUPPORTED_HOSTS)


def download_video(url: str, output_dir: Path, candidate_id: int, max_bytes: int) -> dict:
    if not _supported_url(url):
        raise VideoDownloadError("자동 영상 가져오기는 Instagram, TikTok, YouTube URL만 지원합니다.")
    if yt_dlp is None:
        raise VideoDownloadError("서버에 yt-dlp가 설치되지 않았습니다.")
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"candidate-{candidate_id}-%(id)s"
    def enforce_size(progress: dict) -> None:
        downloaded = int(progress.get("downloaded_bytes") or 0)
        if downloaded > max_bytes:
            raise VideoDownloadError("다운로드 중 영상이 60MB 제한을 초과했습니다.")

    options = {
        "outtmpl": str(output_dir / f"{stem}.%(ext)s"),
        "format": "best[ext=mp4][filesize<60M]/best[filesize<60M]/best[ext=mp4]/best",
        "max_filesize": max_bytes,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "socket_timeout": 30,
        "retries": 2,
        "progress_hooks": [enforce_size],
    }
    cookie_file = os.environ.get("SOURCE_SCOUT_YTDLP_COOKIE_FILE", "").strip()
    if cookie_file:
        path = Path(cookie_file).expanduser()
        if path.is_file():
            options["cookiefile"] = str(path)
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            path = Path(downloader.prepare_filename(info))
    except Exception as exc:
        message = str(exc).replace("ERROR: ", "").strip()
        raise VideoDownloadError(f"영상 자동 가져오기에 실패했습니다: {message[:700]}") from exc
    if not path.is_file():
        candidates = sorted(output_dir.glob(f"candidate-{candidate_id}-*"), key=lambda item: item.stat().st_mtime, reverse=True)
        path = candidates[0] if candidates else path
    if not path.is_file():
        raise VideoDownloadError("다운로드가 끝났지만 영상 파일을 찾지 못했습니다.")
    if path.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv"}:
        path.unlink(missing_ok=True)
        raise VideoDownloadError("가져온 파일이 지원되는 영상 형식이 아닙니다.")
    size = path.stat().st_size
    if size <= 0 or size > max_bytes:
        path.unlink(missing_ok=True)
        raise VideoDownloadError("가져온 영상이 비어 있거나 60MB 제한을 초과했습니다.")
    return {
        "path": path,
        "filename": str(info.get("title") or path.name)[:220] + path.suffix,
        "size": size,
    }

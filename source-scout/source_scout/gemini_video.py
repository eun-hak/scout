from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class GeminiVideoError(Exception):
    pass


IDEA_SCHEMA = {
    "type": "object",
    "required": ["summary", "timeline", "interesting_points", "ideas", "research_needed"],
    "properties": {
        "summary": {"type": "string"},
        "timeline": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["start", "end", "event", "importance"],
                "properties": {
                    "start": {"type": "number"}, "end": {"type": "number"},
                    "event": {"type": "string"}, "importance": {"type": "integer"},
                },
            },
        },
        "interesting_points": {"type": "array", "items": {"type": "string"}},
        "ideas": {
            "type": "array", "minItems": 3, "maxItems": 5,
            "items": {
                "type": "object",
                "required": ["title", "angle", "one_line_pitch", "hook_ideas", "story_flow", "recommended_segments", "target_duration", "strengths", "research_needed", "risk_notes", "score"],
                "properties": {
                    "title": {"type": "string"}, "angle": {"type": "string"},
                    "one_line_pitch": {"type": "string"},
                    "hook_ideas": {"type": "array", "items": {"type": "string"}},
                    "story_flow": {"type": "array", "items": {"type": "string"}},
                    "recommended_segments": {
                        "type": "array", "items": {
                            "type": "object", "required": ["start", "end", "purpose"],
                            "properties": {"start": {"type": "number"}, "end": {"type": "number"}, "purpose": {"type": "string"}},
                        },
                    },
                    "target_duration": {"type": "integer"},
                    "strengths": {"type": "array", "items": {"type": "string"}},
                    "research_needed": {"type": "array", "items": {"type": "string"}},
                    "risk_notes": {"type": "array", "items": {"type": "string"}},
                    "score": {"type": "integer"},
                },
            },
        },
        "research_needed": {"type": "array", "items": {"type": "string"}},
    },
}


PROMPT = """당신은 한국 유튜브 쇼츠의 소재 리서치 에디터입니다.
첨부 영상을 시각 정보와 음성을 함께 관찰하세요. 완성 대본을 쓰지 말고, 이 영상을 어떤 관점으로 풀 수 있는지 서로 겹치지 않는 아이디어 3~5개를 제안하세요.

규칙:
1. 영상에서 직접 확인되는 사실과 추정을 구분합니다.
2. 인물의 신원, 장소, 가격, 연식, 원리처럼 확인할 수 없는 내용은 research_needed에 넣습니다.
3. 각 아이디어는 결과 궁금증, 과정 설명, 원리, 반전, 직업·문화, 감정 등 서로 다른 각도를 사용합니다.
4. 추천 구간은 초 단위 start/end로 작성하고 실제 영상 범위를 벗어나지 않습니다.
5. hook_ideas는 완성 대본이 아니라 첫 문장 방향을 최대 3개 제안합니다.
6. 저작권이나 사용 허락이 확보됐다고 가정하지 않습니다.
7. 모든 설명은 자연스러운 한국어로 작성합니다.
8. score는 이 영상과 아이디어의 적합도를 0~100으로 평가합니다.
"""


def _upload_file(path: Path, mime_type: str, key: str) -> tuple[str, str]:
    size = path.stat().st_size
    start = Request(
        "https://generativelanguage.googleapis.com/upload/v1beta/files",
        data=json.dumps({"file": {"display_name": path.name}}).encode(), method="POST",
        headers={
            "Content-Type": "application/json", "x-goog-api-key": key,
            "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
        },
    )
    with urlopen(start, timeout=30) as response:
        upload_url = response.headers.get("X-Goog-Upload-URL", "")
    if not upload_url:
        raise GeminiVideoError("Gemini 파일 업로드 주소를 받지 못했습니다.")
    upload = Request(
        upload_url, data=path.read_bytes(), method="POST",
        headers={
            "Content-Length": str(size), "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize", "Content-Type": mime_type,
        },
    )
    with urlopen(upload, timeout=180) as response:
        file_info = json.loads(response.read()).get("file", {})
    name, uri = str(file_info.get("name") or ""), str(file_info.get("uri") or "")
    for _ in range(36):
        status_request = Request(
            f"https://generativelanguage.googleapis.com/v1beta/{name}",
            headers={"x-goog-api-key": key},
        )
        with urlopen(status_request, timeout=30) as response:
            status = json.loads(response.read()).get("state", "")
        if status == "ACTIVE":
            return name, uri
        if status == "FAILED":
            raise GeminiVideoError("Gemini가 업로드 영상을 처리하지 못했습니다.")
        time.sleep(5)
    raise GeminiVideoError("Gemini 영상 처리 대기 시간이 초과되었습니다.")


def _delete_file(name: str, key: str) -> None:
    if not name:
        return
    try:
        urlopen(Request(
            f"https://generativelanguage.googleapis.com/v1beta/{name}", method="DELETE",
            headers={"x-goog-api-key": key},
        ), timeout=20).close()
    except (HTTPError, URLError, TimeoutError, OSError):
        pass


def analyze_video(path: Path, api_key: str | None = None, model: str | None = None) -> dict:
    key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    if not key:
        raise GeminiVideoError("Gemini API 키가 설정되지 않았습니다.")
    model_name = (model or os.environ.get("SOURCE_SCOUT_GEMINI_MODEL", "gemini-3.5-flash-lite")).strip()
    mime_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    uploaded_name = ""
    if path.stat().st_size < 18 * 1024 * 1024:
        video_part = {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(path.read_bytes()).decode("ascii")}}
    else:
        try:
            uploaded_name, uploaded_uri = _upload_file(path, mime_type, key)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise GeminiVideoError("Gemini에 분석 영상을 업로드하지 못했습니다.") from exc
        video_part = {"fileData": {"mimeType": mime_type, "fileUri": uploaded_uri}}
    payload = {
        "contents": [{"role": "user", "parts": [
            {"text": PROMPT},
            video_part,
        ]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": IDEA_SCHEMA,
        },
    }
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": key, "User-Agent": "SourceScout/0.3"},
    )
    try:
        with urlopen(request, timeout=240) as response:
            result = json.loads(response.read())
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("error", {}).get("message", "")
        except (json.JSONDecodeError, AttributeError):
            detail = ""
        raise GeminiVideoError(detail or f"Gemini 요청에 실패했습니다. ({exc.code})") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise GeminiVideoError("Gemini 영상 분석 서버에 연결할 수 없습니다.") from exc
    finally:
        _delete_file(uploaded_name, key)
    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise GeminiVideoError("Gemini가 올바른 분석 결과를 반환하지 않았습니다.") from exc
    if not isinstance(parsed.get("ideas"), list) or len(parsed["ideas"]) < 3:
        raise GeminiVideoError("추천 아이디어가 충분히 생성되지 않았습니다.")
    return parsed

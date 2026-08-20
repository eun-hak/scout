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
    "required": ["summary", "timeline", "interesting_points", "perspective_map", "ideas", "research_needed"],
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
        "perspective_map": {
            "type": "array", "minItems": 6, "maxItems": 10,
            "items": {
                "type": "object",
                "required": ["category", "possibility", "evidence", "verification_needed"],
                "properties": {
                    "category": {"type": "string"},
                    "possibility": {"type": "string"},
                    "evidence": {"type": "string"},
                    "verification_needed": {"type": "boolean"},
                },
            },
        },
        "ideas": {
            "type": "array", "minItems": 6, "maxItems": 8,
            "items": {
                "type": "object",
                "required": ["title", "angle", "perspective_category", "content_type", "why_this_angle", "one_line_pitch", "hook_ideas", "story_flow", "recommended_segments", "target_duration", "strengths", "research_needed", "risk_notes", "score"],
                "properties": {
                    "title": {"type": "string"}, "angle": {"type": "string"},
                    "perspective_category": {"type": "string"},
                    "content_type": {"type": "string"},
                    "why_this_angle": {"type": "string"},
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


PROMPT = """당신은 하나의 영상 소스를 여러 콘텐츠로 재해석하는 한국 유튜브 쇼츠 기획 편집자입니다.
첨부 영상을 시각 정보와 음성을 함께 관찰하세요. 완성 대본을 쓰기 전에 먼저 이 소스에서 가능한 관점을 넓게 탐색하고, 서로 본질적으로 다른 아이디어 6~8개를 제안하세요.

규칙:
1. 영상에서 직접 확인되는 사실과 추정을 구분합니다.
2. 인물의 신원, 장소, 가격, 연식, 원리처럼 확인할 수 없는 내용은 research_needed에 넣습니다.
3. perspective_map에서 최소 6가지 가능성을 먼저 검토하세요. 인물·크리에이터/채널 소개, 편집·제작 기술, 장면·작품 해설, 현상·원리, 트렌드·산업, 문화·심리, 반전·퀴즈, 비평·논쟁, 실용 팁, 성장·비하인드 중 영상에 맞는 관점을 고릅니다.
4. 최종 ideas는 perspective_category가 최대한 겹치지 않아야 합니다. 제목만 바꾼 비슷한 아이디어를 여러 개 만들지 마세요.
5. 영상 속 창작자나 계정 단서가 있으면 '이 영상을 만든 사람/채널은 누구인가'라는 소개형 관점을 반드시 후보로 검토하세요. 단, 유명하다는 주장이나 이력은 영상 또는 제공 맥락에서 확인되지 않으면 사실처럼 쓰지 말고 조사 항목으로 둡니다.
6. content_type은 인물소개, 기술해설, 스토리텔링, 트렌드, 퀴즈, 비평, 정보형, 감정형처럼 결과물의 형식을 명시합니다.
7. why_this_angle에는 이 영상이 그 관점에 적합한 구체적인 장면·음성 단서를 설명합니다.
8. 추천 구간은 초 단위 start/end로 작성하고 실제 영상 범위를 벗어나지 않습니다.
9. hook_ideas는 완성 대본이 아니라 첫 문장 방향을 최대 3개 제안합니다.
10. 저작권이나 사용 허락이 확보됐다고 가정하지 않습니다.
11. 모든 설명은 자연스러운 한국어로 작성합니다.
12. score는 이 영상과 아이디어의 적합도를 0~100으로 평가합니다.
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


def analyze_video(path: Path, api_key: str | None = None, model: str | None = None, context: dict | None = None) -> dict:
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
    context = context or {}
    context_text = "\n".join(
        f"- {label}: {str(context.get(key) or '정보 없음')[:1000]}"
        for key, label in (("title", "후보 제목"), ("creator", "게시자/계정"), ("url", "원본 URL"), ("notes", "수집된 설명"))
    )
    payload = {
        "contents": [{"role": "user", "parts": [
            {"text": f"{PROMPT}\n수집 단계에서 함께 확보된 맥락:\n{context_text}\n이 맥락도 확정 사실과 추정을 구분해 사용하세요."},
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
    if not isinstance(parsed.get("ideas"), list) or len(parsed["ideas"]) < 6:
        raise GeminiVideoError("추천 아이디어가 충분히 생성되지 않았습니다.")
    return parsed

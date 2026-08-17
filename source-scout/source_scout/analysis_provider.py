from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

from .analyzer import analyze_metadata


def _local_result(candidate: dict) -> dict:
    suggestion = analyze_metadata(candidate["title"], candidate["notes"], candidate["creator"], candidate["platform"])
    title = candidate["title"]
    ideas = [
        f"왜 이런 일이 벌어졌을까: {title}",
        f"끝까지 보면 이해되는 과정: {title}",
        f"한국에서는 보기 힘든 장면: {title}",
    ]
    return {
        **suggestion,
        "analysis_status": "metadata_only",
        "analysis_detail": "제목·설명·게시자 정보만 분석했습니다. 영상 화면과 음성은 아직 분석하지 않았습니다.",
        "script_ideas": ideas,
    }


def analyze_candidate(candidate: dict, timeout: float = 120.0) -> dict:
    webhook = os.environ.get("SOURCE_SCOUT_ANALYSIS_WEBHOOK", "").strip()
    if not webhook:
        return _local_result(candidate)
    token = os.environ.get("SOURCE_SCOUT_ANALYSIS_TOKEN", "").strip()
    payload = json.dumps({
        "candidate_id": candidate["id"],
        "url": candidate["url"],
        "platform": candidate["platform"],
        "title": candidate["title"],
        "creator": candidate["creator"],
        "description": candidate["notes"],
        "thumbnail_url": candidate["thumbnail_url"],
    }, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(webhook, data=payload, headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read(2_000_000))
    if not isinstance(result, dict):
        raise ValueError("분석 서버가 JSON 객체를 반환하지 않았습니다.")
    result["analysis_status"] = "complete"
    result.setdefault("analysis_detail", "외부 영상 분석 서버에서 화면·음성 분석을 완료했습니다.")
    result.setdefault("script_ideas", [])
    return result

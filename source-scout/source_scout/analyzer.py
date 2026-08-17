from __future__ import annotations

import re

THEME_KEYWORDS = {
    "직업·공정": ("worker", "process", "factory", "craft", "repair", "restore", "build", "making", "작업", "공정", "장인", "수리", "복원"),
    "진위 검증": ("fake", "real or", "staged", "fact check", "debunk", "진짜", "가짜", "주작", "검증"),
    "감동 스토리": ("kindness", "surprise", "reunion", "helped", "gift", "wholesome", "감동", "선행", "재회", "선물"),
    "동물": ("dog", "cat", "animal", "pet", "wildlife", "puppy", "kitten", "강아지", "고양이", "동물", "반려"),
    "과학·원리": ("science", "experiment", "why", "how it works", "engineering", "과학", "실험", "원리", "이유"),
}
HOOK_WORDS = ("amazing", "incredible", "unexpected", "never", "secret", "caught", "놀라", "반전", "비밀", "결국")
EXPLAIN_WORDS = ("why", "how", "process", "technique", "method", "because", "원리", "이유", "방법", "과정")
NOVEL_WORDS = ("unusual", "rare", "unique", "traditional", "unknown", "특이", "희귀", "전통", "처음")
RISK_WORDS = ("blood", "death", "dead", "accident", "weapon", "fight", "movie", "football", "child", "피", "사망", "사고", "무기", "싸움", "영화", "축구", "아동")


def _hits(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for word in words if word in text)


def _rating(base: int, hits: int) -> int:
    return max(1, min(5, base + min(2, hits)))


def analyze_metadata(title: str, description: str, creator: str, platform: str) -> dict:
    """공개 페이지 메타데이터만 이용하는 보수적인 1차 제안입니다."""
    combined = re.sub(r"\s+", " ", f"{title} {description}").strip().lower()
    theme_scores = {theme: _hits(combined, words) for theme, words in THEME_KEYWORDS.items()}
    best_theme, best_hits = max(theme_scores.items(), key=lambda item: item[1])
    theme = best_theme if best_hits else "기타"
    risk_hits = _hits(combined, RISK_WORDS)
    description_length = len(description.strip())
    scores = {
        "hook_score": _rating(2, _hits(combined, HOOK_WORDS)),
        "explainability_score": _rating(2, _hits(combined, EXPLAIN_WORDS) + (1 if theme in {"직업·공정", "과학·원리", "진위 검증"} else 0)),
        "novelty_score": _rating(2, _hits(combined, NOVEL_WORDS)),
        "editability_score": 4 if description_length >= 80 else 3 if description_length >= 25 else 2,
        "traceability_score": 4 if creator.strip() else 2,
        "risk_score": min(5, 1 + risk_hits),
    }
    reasons = [f"메타데이터에서 '{theme}' 테마를 우선 제안", "게시자 정보 감지" if creator.strip() else "원작자 확인 필요"]
    if risk_hits:
        reasons.append(f"위험 키워드 {risk_hits}개 감지")
    if description_length < 25:
        reasons.append("설명이 짧아 영상 직접 검토 필요")
    reasons.append(f"{platform} 페이지의 공개 메타데이터만 분석")
    return {"theme": theme, **scores, "analysis_summary": " · ".join(reasons)}

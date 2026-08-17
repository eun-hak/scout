from __future__ import annotations

SCORE_FIELDS = (
    "hook_score",
    "explainability_score",
    "novelty_score",
    "editability_score",
    "traceability_score",
    "risk_score",
)

WEIGHTS = {
    "hook_score": 0.25,
    "explainability_score": 0.25,
    "novelty_score": 0.20,
    "editability_score": 0.15,
    "traceability_score": 0.15,
}


def clamp_rating(value: object, default: int = 3) -> int:
    try:
        rating = int(value)
    except (TypeError, ValueError):
        rating = default
    return max(1, min(5, rating))


def calculate_score(values: dict[str, object]) -> float:
    weighted = sum(clamp_rating(values.get(field)) * weight for field, weight in WEIGHTS.items())
    base = weighted * 20
    risk_penalty = (clamp_rating(values.get("risk_score")) - 1) * 5
    return round(max(0, min(100, base - risk_penalty)), 1)


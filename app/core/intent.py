from dataclasses import dataclass

from app.core.taxonomy import classify_query_type


INTENT_KEYWORDS: dict[str, list[str]] = {
    "summarize": ["요약", "정리", "summary", "summarize", "recap"],
    "analyze": ["분석", "왜", "원인", "이유", "analyze", "analysis", "진단"],
    "design": ["설계", "아키텍처", "구조", "design", "architecture", "문서"],
    "coding": ["코드", "구현", "함수", "클래스", "버그", "오류", "fix", "debug", "api"],
    "compare": ["비교", "차이", "vs", "compare", "trade-off", "트레이드오프"],
    "explain": ["설명", "뭐야", "뭔지", "explain", "what is"],
    "decide": ["선택", "결정", "추천", "decide", "recommend"],
    "extract": ["추출", "뽑아", "찾아", "extract", "find"],
    "predict": ["예측", "전망", "가능성", "predict", "forecast"],
}

REASONING_MODE_MAP: dict[str, str] = {
    "summarize": "summary",
    "analyze": "analysis",
    "design": "architecture_design",
    "coding": "code_implementation",
    "compare": "comparative_analysis",
    "explain": "explanation",
    "decide": "decision_making",
    "extract": "extraction",
    "predict": "prediction",
    "continue_discussion": "general",
}


@dataclass(frozen=True)
class IntentResult:
    primary_intent: str
    secondary_intents: list[str]
    confidence: float
    reasoning_mode: str
    requires_recent_context: bool
    requires_memory: bool
    requires_structured_output: bool
    query_type: str = "what"


def analyze_intent(message: str) -> IntentResult:
    message_lower = message.lower()
    query_type = classify_query_type(message)
    scores: dict[str, int] = {}

    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in message_lower)
        if score:
            scores[intent] = score

    if not scores:
        return IntentResult(
            primary_intent="continue_discussion",
            secondary_intents=[],
            confidence=0.4,
            reasoning_mode="general",
            requires_recent_context=True,
            requires_memory=False,
            requires_structured_output=False,
            query_type=query_type,
        )

    sorted_intents = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    primary = sorted_intents[0][0]
    secondary = [intent for intent, _ in sorted_intents[1:3]]
    total_score = sum(scores.values())
    confidence = min(0.95, 0.5 + (scores[primary] / total_score) * 0.5)

    return IntentResult(
        primary_intent=primary,
        secondary_intents=secondary,
        confidence=round(confidence, 2),
        reasoning_mode=REASONING_MODE_MAP.get(primary, "general"),
        requires_recent_context=True,
        requires_memory=primary in {"design", "coding", "analyze", "summarize"},
        requires_structured_output=primary in {"design", "summarize", "compare", "analyze"},
        query_type=query_type,
    )

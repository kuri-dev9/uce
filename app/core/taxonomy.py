"""
Taxonomy system for query-type classification and retrieval boosting.
Rule-based, deterministic. No LLM calls.
"""

import re


QUERY_TYPE_RULES: dict[str, list[str]] = {
    "where": ["어디", "어디서", "where", "위치", "실행", "수행", "동작", "어느"],
    "what": ["뭐야", "무엇", "what", "정의", "설명", "소개", "역할", "란", "이란"],
    "how": ["어떻게", "방법", "how", "절차", "과정", "단계"],
    "config": ["설정", "환경변수", "config", ".env", "options"],
    "api": ["api", "endpoint", "curl", "호출", "요청", "엔드포인트"],
    "troubleshooting": ["오류", "에러", "error", "문제", "실패", "안 됨"],
}

GENERIC_QUERY_WORDS = {"what", "how", "where", "is", "are", "the", "a", "an", "explain", "about"}

SECTION_TAXONOMY_KEYWORDS: dict[str, list[str]] = {
    "deployment": ["docker", "compose", "container", "배포", "실행", "run", "service", "port"],
    "architecture": ["구조", "아키텍처", "architecture", "설계", "backend", "middleware"],
    "config": ["설정", "환경변수", "config", ".env", "options", "settings"],
    "api": ["api", "endpoint", "http", "rest", "curl", "route"],
    "runtime": ["런타임", "runtime", "동작", "프로세스", "process"],
    "overview": ["개요", "overview", "소개", "목표", "introduction", "주요", "기능", "역할", "what is"],
    "flow": ["흐름", "flow", "과정", "절차", "단계", "pipeline", "→", "step"],
    "feature": ["기능", "feature", "지원", "support", "특징"],
    "troubleshooting": ["오류", "에러", "error", "문제", "실패", "해결", "fix"],
}

QUERY_TAXONOMY_BOOST: dict[str, dict[str, float]] = {
    "entity": {"overview": 0.24, "architecture": 0.12, "feature": 0.10, "api": 0.08},
    "continuation_query": {"overview": 0.18, "flow": 0.12, "feature": 0.08},
    "implicit_subject_query": {"overview": 0.18, "flow": 0.12, "feature": 0.08},
    "ellipsis_query": {"overview": 0.16, "flow": 0.10, "feature": 0.08},
    "where": {"deployment": 0.15, "runtime": 0.10, "architecture": 0.08},
    "what": {"overview": 0.20, "architecture": 0.10, "feature": 0.08},
    "how": {"flow": 0.12, "architecture": 0.08, "feature": 0.06},
    "config": {"config": 0.20, "deployment": 0.08},
    "api": {"api": 0.20, "flow": 0.08},
    "troubleshooting": {"troubleshooting": 0.18, "config": 0.08},
}


def classify_query_type(message: str) -> str:
    """규칙 기반 query type 분류. LLM 불필요."""
    raw_tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_+-]*", message or "")
    if len((message or "").strip().split()) <= 4:
        entity_tokens = [
            token
            for token in raw_tokens
            if len(token) >= 2
            and token.lower() not in GENERIC_QUERY_WORDS
            and (any(char.isalpha() for char in token) or any(char.isdigit() for char in token))
        ]
        if entity_tokens:
            return "entity"

    lower = (message or "").lower()
    for query_type, keywords in QUERY_TYPE_RULES.items():
        if any(keyword in lower for keyword in keywords):
            return query_type
    return "what"


def classify_chunk_taxonomy(content: str, header_path: str) -> tuple[str, ...]:
    """청크의 taxonomy 분류. 복수 해당 가능."""
    combined = f"{header_path or ''} {content or ''}".lower()
    matched = []
    for section_type, keywords in SECTION_TAXONOMY_KEYWORDS.items():
        if any(keyword in combined for keyword in keywords):
            matched.append(section_type)
    return tuple(matched)


def apply_taxonomy_boost(score: float, taxonomy: tuple[str, ...], query_type: str) -> float:
    """taxonomy 기반 score boosting. semantic retrieval의 reranking signal."""
    boosts = QUERY_TAXONOMY_BOOST.get(query_type, {})
    bonus = sum(boosts.get(section_type, 0.0) for section_type in taxonomy)
    return min(1.0, score + bonus)

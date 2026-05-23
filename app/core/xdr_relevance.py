"""
Lightweight xDR relevance detection based on schema field names and aliases.
No LLM, no complex semantic engine — simple token overlap scoring.
"""
from __future__ import annotations
import re

_GENERIC_TOKENS = {
    "정보", "내용", "진행", "상황", "문제", "데이터",
    "결과", "현황", "분석", "통계", "조회", "확인",
    "보여", "알려", "어떻게", "무엇", "어디",
}

_NOT_XDR_PATTERNS = [
    r"^(안녕|hello|hi|hey)\b",
    r"^(고마워|감사|thanks)\b",
    r"^(ㅋ+|ㅎ+|ㅠ+|ㅜ+)",
    r"^(오케이|ok|알겠|알았)\b",
    r"너는\s*(누구|뭐야|어떤)",
    r"(날씨|주식|뉴스|맛집|영화)",
]


def compute_xdr_relevance(
    query: str,
    schema_hints: list[dict],
    threshold: float = 1.5,
) -> tuple[bool, float]:
    """
    query가 xDR 조사 질문인지 schema 기반으로 판단.

    반환: (is_xdr_related, score)
    - schema_hints: [{"field_name": str, "group": str, "aliases": list[str]}]
    - threshold: 기본 1.5 (alias 2개 매칭 또는 field_name 1개 + alias 1개)
    """
    query_lower = query.lower().strip()

    for pattern in _NOT_XDR_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return False, 0.0

    if not schema_hints:
        return False, 0.0

    score = 0.0
    for field in schema_hints:
        field_name = str(field.get("field_name", "")).lower()
        group = str(field.get("group") or "").lower()
        aliases = [str(a).lower() for a in (field.get("aliases") or [])]

        if field_name and field_name in query_lower:
            weight = 0.5 if field_name in _GENERIC_TOKENS else 1.0
            score += weight

        if group and group in query_lower:
            weight = 0.3 if group in _GENERIC_TOKENS else 0.6
            score += weight

        for alias in aliases:
            if not alias or len(alias) < 2:
                continue
            if alias in query_lower:
                weight = 0.3 if alias in _GENERIC_TOKENS else 0.8
                score += weight

    is_related = score >= threshold
    return is_related, round(score, 2)

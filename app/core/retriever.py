import re
from dataclasses import dataclass

from app.api.schemas import Message
from app.core.taxonomy import apply_taxonomy_boost, classify_chunk_taxonomy


@dataclass(frozen=True)
class ContextItem:
    id: str
    source: str
    role: str
    content: str
    score: float
    reason: str
    score_breakdown: dict[str, float]
    item_type: str = "context"
    prompt_content: str | None = None
    importance: float = 0.5
    metadata: dict | None = None
    taxonomy: tuple[str, ...] = ()
    drop_reason: str | None = None


CONSTRAINT_MARKERS = ["반드시", "필수", "절대 금지", "해야 한다", "제약", "유지"]
DECISION_MARKERS = ["결정", "확정", "채택", "하기로 함", "하기로 했다", "하기로 결정", "선택", "배제"]
OVERVIEW_MARKERS = ["overview", "summary", "goals", "목표", "개요", "요약", "phase 계획", "phase", "architecture", "constraints", "제약"]
CODING_MARKERS = ["error", "traceback", "파일", "함수", "class", "api", "endpoint", "expected", "actual", "구현"]
SUMMARY_MARKERS = ["요약", "정리", "결정", "미결", "다음", "chronology"]
HEADING_STOPWORDS = {"uce"}
GOAL_QUERY_MARKERS = {"목표", "목적", "뭐야", "무엇", "왜", "이유", "정의", "개요"}


def retrieve_context(
    current_message: Message,
    recent_messages: list[Message],
    intent_name: str = "continue_discussion",
    max_items: int = 15,
) -> list[ContextItem]:
    if not recent_messages:
        return []

    bounded_messages = recent_messages[-max_items:]
    query_words = set(tokenize(current_message.content))
    results: list[ContextItem] = []

    for index, message in enumerate(bounded_messages):
        score, breakdown, reason = score_text(
            query_words=query_words,
            content=message.content,
            heading_text="",
            section_path_text="",
            recency_score=(index + 1) / len(bounded_messages),
            role=message.role,
            importance=0.5,
            intent_name=intent_name,
        )
        results.append(
            ContextItem(
                id=message.id or f"msg_{index}",
                source="recent_message",
                role=message.role,
                content=message.content,
                score=round(score, 4),
                reason=reason,
                score_breakdown=breakdown,
                item_type="message",
                importance=0.5,
            )
        )

    return sorted(results, key=lambda item: item.score, reverse=True)


def retrieve_document_chunks(
    current_message: Message,
    chunks,
    intent_name: str = "continue_discussion",
    query_type: str = "what",
) -> list[ContextItem]:
    query_words = set(tokenize(current_message.content))
    results: list[ContextItem] = []
    for section in chunks:
        descendant_titles = " ".join(section.metadata.get("descendant_titles", []))
        section_path_text = str(section.metadata.get("header_path", ""))
        heading_text = " ".join(part for part in [section_path_text, descendant_titles] if part)
        taxonomy = classify_chunk_taxonomy(section.content, section_path_text)
        score, breakdown, reason = score_text(
            query_words=query_words,
            content=section.content,
            heading_text=heading_text,
            section_path_text=section_path_text,
            recency_score=0.5,
            role="document",
            importance=section.importance,
            intent_name=intent_name,
            heading_level=section.heading_level,
        )
        boosted_score = apply_taxonomy_boost(score, taxonomy, query_type)
        taxonomy_boost = round(boosted_score - score, 4)
        if taxonomy_boost:
            breakdown = {
                **breakdown,
                "taxonomy_boost": taxonomy_boost,
                "final_score": round(boosted_score, 4),
            }
            reason = f"{reason}, taxonomy boost: {query_type}->{', '.join(taxonomy)}"
        else:
            breakdown = {**breakdown, "taxonomy_boost": 0.0}
        results.append(
            ContextItem(
                id=section.id,
                source=f"document:{section.source}",
                role="document",
                content=section.content,
                score=round(boosted_score, 4),
                reason=reason,
                score_breakdown=breakdown,
                item_type="document_section",
                prompt_content=section.prompt_content,
                importance=section.importance,
                metadata={**section.metadata, "query_words": sorted(query_words)},
                taxonomy=taxonomy,
            )
        )
    return sorted(results, key=lambda item: item.score, reverse=True)


def score_text(
    query_words: set[str],
    content: str,
    heading_text: str,
    section_path_text: str,
    recency_score: float,
    role: str,
    importance: float,
    intent_name: str,
    heading_level: int = 0,
) -> tuple[float, dict[str, float], str]:
    expanded_query_words = expand_query_words(query_words)
    content_words = set(tokenize(content))
    heading_words = set(tokenize(heading_text))
    heading_query_words = {word for word in expanded_query_words if not word.isdigit() and word not in HEADING_STOPWORDS}
    significant_heading_words = {word for word in heading_words if not word.isdigit() and word not in HEADING_STOPWORDS}
    overlap = len(query_words & content_words)
    semantic_score = overlap / len(query_words) if query_words else 0.0
    heading_overlap = len(heading_query_words & significant_heading_words)
    heading_score = heading_overlap / len(heading_query_words) if heading_query_words else 0.0
    if heading_overlap:
        heading_score = min(1.0, heading_score + 0.4)
    heading_score = min(1.0, heading_score + phrase_heading_boost(query_words, heading_text))
    heading_depth = heading_text.count(">") + 1 if heading_text else 0
    section_priority_score = section_priority(section_path_text, expanded_query_words)
    section_coherence_score = section_coherence(content=content, heading_level=heading_level)
    constraint_score = marker_score(content, CONSTRAINT_MARKERS)
    decision_score = marker_score(content, DECISION_MARKERS)
    if intent_name in {"explain", "continue_discussion"}:
        if role == "document":
            role_score = 0.85
        elif role == "user":
            role_score = 0.40
        else:
            role_score = 0.45
    else:
        role_score = 0.8 if role == "user" else 0.55 if role == "assistant" else 0.65
    importance_score = importance
    intent_alignment_score = intent_alignment(
        content=content,
        heading_text=section_path_text or heading_text,
        intent_name=intent_name,
        query_words=expanded_query_words,
    )
    final_score = (
        0.35 * heading_score
        + 0.20 * section_coherence_score
        + 0.18 * semantic_score
        + 0.12 * intent_alignment_score
        + 0.08 * recency_score
        + 0.07 * constraint_score
        + 0.05 * role_score
    )
    final_score = final_score + (0.05 * decision_score) + (0.12 * section_priority_score)
    final_score += exact_heading_priority(section_path_text, expanded_query_words)
    mismatch_penalty = phase_mismatch_penalty(query_words, section_path_text)
    final_score -= mismatch_penalty
    final_score = (final_score * 0.9) + (importance_score * 0.1)
    if (
        intent_name in {"explain", "summarize", "continue_discussion"}
        and heading_depth > 2
        and exact_heading_priority(section_path_text, expanded_query_words) == 0.0
    ):
        final_score -= min(0.18, 0.08 * (heading_depth - 2))
    final_score = min(1.0, final_score)
    breakdown = {
        "semantic_score": round(semantic_score, 4),
        "heading_score": round(heading_score, 4),
        "section_path_score": round(heading_score, 4),
        "heading_depth": heading_depth,
        "section_priority_score": round(section_priority_score, 4),
        "section_coherence_score": round(section_coherence_score, 4),
        "mismatch_penalty": round(mismatch_penalty, 4),
        "recency_score": round(recency_score, 4),
        "intent_alignment_score": round(intent_alignment_score, 4),
        "constraint_score": round(constraint_score, 4),
        "decision_score": round(decision_score, 4),
        "role_score": round(role_score, 4),
        "importance_score": round(importance_score, 4),
        "final_score": round(final_score, 4),
    }
    reasons = [
        f"overlap={overlap}",
        f"heading_overlap={heading_overlap}",
        f"heading_level={heading_level}",
        f"recency={round(recency_score, 2)}",
    ]
    if heading_overlap:
        reasons.append(f"heading direct match: {', '.join(sorted(heading_query_words & significant_heading_words))}")
    if section_priority_score:
        reasons.append("section priority boost")
    if section_coherence_score:
        reasons.append("section coherence preserved")
    if exact_heading_priority(section_path_text, expanded_query_words):
        reasons.append("exact overview heading boost")
    if mismatch_penalty:
        reasons.append("phase mismatch penalty")
    if (
        intent_name in {"explain", "summarize", "continue_discussion"}
        and heading_depth > 2
        and exact_heading_priority(section_path_text, expanded_query_words) == 0.0
    ):
        reasons.append("deep subsection penalty")
    if intent_alignment_score:
        reasons.append(f"intent alignment: {intent_name}")
    if constraint_score:
        reasons.append("constraint marker detected")
    if decision_score:
        reasons.append("decision marker detected")
    return final_score, breakdown, ", ".join(reasons)


def marker_score(text: str, markers: list[str]) -> float:
    if not text:
        return 0.0
    count = sum(1 for marker in markers if marker in text)
    if count == 0:
        return 0.0
    return min(1.0, 0.45 + 0.2 * count)


def section_priority(heading_text: str, query_words: set[str] | None = None) -> float:
    lowered = heading_text.lower()
    if query_words:
        heading_words = {word for word in tokenize(heading_text) if not word.isdigit()}
        query_terms = {word for word in query_words if not word.isdigit()}
        direct_match = len(query_terms & heading_words) / len(query_terms) if query_terms else 0.0
        if direct_match >= 0.3:
            return min(1.0, 0.5 + direct_match)
    count = sum(1 for marker in overview_markers_for_query(query_words) if marker in lowered)
    if count == 0:
        return 0.0
    return min(1.0, 0.35 + 0.2 * count)


def section_coherence(content: str, heading_level: int) -> float:
    if not content:
        return 0.0
    length = len(content)
    if heading_level in {1, 2}:
        base = 0.8
    elif heading_level == 3:
        base = 0.55
    else:
        base = 0.35
    if length < 120:
        base -= 0.25
    elif 300 <= length <= 6000:
        base += 0.15
    elif length > 10000:
        base -= 0.1
    return max(0.0, min(1.0, base))


def exact_heading_priority(heading_text: str, query_words: set[str] | None = None) -> float:
    lowered = heading_text.lower()
    requested_phase = requested_phase_number(query_words or set())
    if requested_phase and "phase 계획" in lowered and "phase 2: practical context engineering" in lowered:
        return 0.2
    if requested_phase and "phase 2: practical context engineering" in lowered:
        return 0.16
    if requested_phase and "phase 계획" in lowered:
        return 0.1
    if query_words and query_words & GOAL_QUERY_MARKERS:
        if "project overview" in lowered or "overview" in lowered:
            return 0.34
        if "핵심 원칙" in lowered:
            return 0.18
        if "문제 정의" in lowered:
            return 0.1
    return 0.0


def phase_mismatch_penalty(query_words: set[str], heading_text: str) -> float:
    lowered = heading_text.lower()
    requested_phase = requested_phase_number(query_words)
    heading_phases = set(re.findall(r"phase\s+(\d+)", lowered))
    if requested_phase and heading_phases and requested_phase not in heading_phases:
        return 0.34
    if requested_phase == "2" and "future architecture" in lowered:
        return 0.34
    if not requested_phase and (query_words & GOAL_QUERY_MARKERS) and "phase" in lowered:
        return 0.14
    return 0.0


def requested_phase_number(query_words: set[str]) -> str | None:
    if "phase" not in query_words:
        return None
    for word in query_words:
        if word.isdigit():
            return word
    return None


def phrase_heading_boost(query_words: set[str], heading_text: str) -> float:
    if not query_words or not heading_text:
        return 0.0
    lowered = heading_text.lower()
    boost = 0.0
    query_terms = sorted(query_words, key=len, reverse=True)
    for term in query_terms:
        if len(term) >= 2 and term in lowered:
            boost += 0.12
    if {"phase", "2"} <= query_words and "phase 2" in lowered:
        boost += 0.35
    return min(0.45, boost)


def intent_alignment(
    content: str,
    heading_text: str,
    intent_name: str,
    query_words: set[str] | None = None,
) -> float:
    combined = f"{heading_text}\n{content}".lower()
    if intent_name in {"explain", "continue_discussion"}:
        heading_lower = heading_text.lower()
        markers = overview_markers_for_query(query_words)
        heading_hit = any(marker in heading_lower for marker in markers)
        content_hit = marker_score(combined, markers)
        return min(1.0, (0.7 if heading_hit else 0.0) + (content_hit * 0.3))
    if intent_name == "summarize":
        return marker_score(combined, SUMMARY_MARKERS + OVERVIEW_MARKERS)
    if intent_name == "coding":
        return marker_score(combined, CODING_MARKERS)
    if intent_name == "design":
        return max(marker_score(combined, OVERVIEW_MARKERS), marker_score(combined, CONSTRAINT_MARKERS + DECISION_MARKERS))
    if intent_name == "analyze":
        return marker_score(combined, ["근거", "원인", "왜냐하면", "리스크", "ambiguity", "evidence", "cause"])
    return 0.0


def tokenize(text: str) -> list[str]:
    return re.findall(r"[가-힣a-zA-Z0-9_]+", text.lower())


def expand_query_words(query_words: set[str]) -> set[str]:
    expanded = set(query_words)
    for word in query_words:
        match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)", word)
        if match:
            expanded.add(match.group(1).lower())
    if "목적" in query_words:
        expanded.add("목표")
    if "목표" in query_words:
        expanded.add("목적")
    if "뭐야" in query_words:
        expanded.update({"개요", "목표"})
    return expanded


def overview_markers_for_query(query_words: set[str] | None) -> list[str]:
    markers = list(OVERVIEW_MARKERS)
    if not requested_phase_number(query_words or set()):
        markers = [marker for marker in markers if marker not in {"phase", "phase 계획"}]
    return markers

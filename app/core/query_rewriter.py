import re
from dataclasses import dataclass

from app.api.schemas import ConversationState, Message
from app.core.retriever import normalize_text_tokens


CONTINUATION_MARKERS = [
    "그건",
    "그거",
    "그럼",
    "그러면",
    "이건",
    "이거",
    "해당",
    "관련",
    "이후",
    "결과",
    "반응",
    "과정",
    "현황",
    "입장",
    "주장",
    "내용",
]

QUESTION_SUFFIXES = ("은", "는", "어때", "뭐야", "왜", "결과는", "반응은")
ENTITY_STOPWORDS = {
    "알려줘",
    "어때",
    "뭐야",
    "무엇",
    "설명",
    "과정",
    "결과",
    "반응",
    "주장",
    "협상",
    "내용",
    "관련",
    "소식",
    "현황",
}


@dataclass(frozen=True)
class QueryRewriteResult:
    original_query: str
    rewritten_query: str
    applied: bool
    query_type: str
    reason: str | None


def rewrite_query(
    current_message: Message,
    recent_messages: list[Message],
    previous_state: ConversationState | None,
    topic_confidence: float,
) -> QueryRewriteResult:
    original = current_message.content.strip()
    if not original:
        return QueryRewriteResult(original, original, False, "what", None)

    active_topic = _active_topic(previous_state, recent_messages)
    active_entities = _active_entities(previous_state, recent_messages)
    has_query_entity = bool(_extract_entities(original))
    token_count = len(normalize_text_tokens(original))
    continuation = _is_continuation_query(
        query=original,
        has_query_entity=has_query_entity,
        token_count=token_count,
        active_topic=active_topic,
        topic_confidence=max(topic_confidence, previous_state.topic_confidence if previous_state else 0.0),
    )

    if not continuation:
        return QueryRewriteResult(original, original, False, "what", None)

    prefix_parts = []
    if active_topic:
        prefix_parts.append(active_topic)
    for entity in active_entities[:3]:
        if entity not in " ".join(prefix_parts):
            prefix_parts.append(entity)

    prefix = " ".join(prefix_parts).strip()
    if not prefix:
        return QueryRewriteResult(original, original, False, "what", None)

    rewritten = f"{prefix} {original}"
    return QueryRewriteResult(
        original_query=original,
        rewritten_query=rewritten,
        applied=True,
        query_type=_continuation_query_type(original),
        reason="implicit subject resolved from conversation state",
    )


def infer_active_topic(
    current_message: Message,
    recent_messages: list[Message],
    previous_state: ConversationState | None,
) -> tuple[str | None, list[str], float]:
    current_entities = _extract_entities(current_message.content)
    recent_entities = _active_entities(previous_state, recent_messages)
    entities = _dedupe([*current_entities, *recent_entities])[:8]

    if len(current_entities) >= 2:
        return " ".join(current_entities[:3]), entities, 0.9
    if current_entities and previous_state and previous_state.active_topic:
        return previous_state.active_topic, entities, max(previous_state.topic_confidence, 0.78)
    if current_entities:
        return " ".join(current_entities[:2]), entities, 0.78
    if previous_state and previous_state.active_topic:
        return previous_state.active_topic, entities, previous_state.topic_confidence
    return None, entities, 0.0


def _is_continuation_query(
    *,
    query: str,
    has_query_entity: bool,
    token_count: int,
    active_topic: str | None,
    topic_confidence: float,
) -> bool:
    if not active_topic or topic_confidence < 0.55:
        return False
    compact = query.strip()
    marker_hit = any(marker in compact for marker in CONTINUATION_MARKERS)
    suffix_hit = compact.endswith(QUESTION_SUFFIXES)
    return not has_query_entity and token_count <= 5 and (marker_hit or suffix_hit)


def _continuation_query_type(query: str) -> str:
    if any(marker in query for marker in ("그건", "그거", "이건", "이거", "그 이후")):
        return "implicit_subject_query"
    if len(normalize_text_tokens(query)) <= 3:
        return "ellipsis_query"
    return "continuation_query"


def _active_topic(previous_state: ConversationState | None, recent_messages: list[Message]) -> str | None:
    if previous_state and previous_state.active_topic:
        return previous_state.active_topic
    entities = _active_entities(previous_state, recent_messages)
    return " ".join(entities[:3]) if entities else None


def _active_entities(previous_state: ConversationState | None, recent_messages: list[Message]) -> list[str]:
    entities: list[str] = []
    if previous_state:
        entities.extend(previous_state.active_entities)
        if previous_state.active_topic:
            entities.extend(_extract_entities(previous_state.active_topic))
    for message in reversed(recent_messages[-6:]):
        if message.role == "user":
            entities.extend(_extract_entities(message.content))
    return _dedupe(entities)


def _extract_entities(text: str) -> list[str]:
    tokens = re.findall(r"[가-힣A-Za-z0-9][가-힣A-Za-z0-9_\-]{1,}", text or "")
    entities = []
    for token in tokens:
        stripped = re.sub(r"(은|는|이|가|을|를|의|과|와|로|으로|에|에서|에게|한테|도|만)$", "", token)
        if len(stripped) < 2:
            continue
        if stripped in ENTITY_STOPWORDS:
            continue
        if stripped.isdigit():
            continue
        entities.append(stripped)
    return _dedupe(entities)


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result

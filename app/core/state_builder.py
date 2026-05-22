import re

from app.api.schemas import ConversationState, Memory, Message
from app.core.intent import IntentResult
from app.core.query_rewriter import infer_active_topic


def build_state(
    recent_messages: list[Message],
    current_message: Message,
    intent: IntentResult,
    previous_state: ConversationState | None,
    optional_memories: list[Memory],
) -> ConversationState:
    state = previous_state.model_copy(deep=True) if previous_state else ConversationState()
    state.reasoning_mode = intent.reasoning_mode
    state.active_intent = intent.primary_intent

    active_topic, active_entities, topic_confidence = infer_active_topic(
        current_message=current_message,
        recent_messages=recent_messages,
        previous_state=previous_state,
    )
    if active_topic:
        state.active_topic = active_topic
        state.topic_confidence = max(state.topic_confidence, topic_confidence)
    if active_entities:
        state.active_entities = _merge_unique(state.active_entities, active_entities)[:8]

    project = _guess_project_name(current_message.content)
    if project and (not state.active_project or project == state.active_project):
        state.active_project = project

    if not state.current_focus or intent.primary_intent != "continue_discussion":
        state.current_focus = _compact_focus(current_message.content)

    if not state.user_goal:
        state.user_goal = _goal_from_intent(intent.primary_intent, current_message.content)

    for memory in optional_memories:
        if memory.type == "project_constraint":
            _append_unique(state.important_constraints, memory.content)
        elif memory.type == "decision":
            _append_unique(state.decisions, memory.content)
        elif memory.type == "unresolved_issue":
            _append_unique(state.open_questions, memory.content)

    for message in recent_messages[-5:]:
        if message.role == "user" and "?" in message.content:
            _append_unique(state.open_questions, _compact_focus(message.content, limit=90))

    return state


def _guess_project_name(text: str) -> str | None:
    if "프로젝트" not in text and "project" not in text.lower() and "Universal Context Engine" not in text:
        return None
    upper_words = re.findall(r"\b[A-Z][A-Z0-9_]{1,}\b", text)
    ignored = {"PDF", "API", "JSON", "DB", "LLM", "RAG", "MVP"}
    candidates = [word for word in upper_words if word not in ignored]
    if candidates:
        return candidates[0]
    if "Universal Context Engine" in text:
        return "UCE"
    return None


def _compact_focus(text: str, limit: int = 80) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


def _goal_from_intent(intent: str, message: str) -> str:
    if intent == "design":
        return "기술 설계와 구현 가능한 구조를 정리한다."
    if intent == "coding":
        return "요구사항을 실행 가능한 코드와 API로 구현한다."
    return _compact_focus(message)


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _merge_unique(existing: list[str], incoming: list[str]) -> list[str]:
    merged = list(existing)
    for item in incoming:
        if item and item not in merged:
            merged.append(item)
    return merged

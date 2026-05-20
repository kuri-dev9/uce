from dataclasses import dataclass
from typing import Literal

from app.api.schemas import BuildContextOptions, ConversationState, Message
from app.core.retriever import tokenize


TopicRelation = Literal["continue_topic", "related_topic", "ambiguous", "new_topic"]
ContextPolicy = Literal["full_context", "focused_context", "minimal_context", "fresh_context"]

SHIFT_MARKERS = [
    "근데",
    "그런데",
    "갑자기",
    "다른 얘기",
    "다른 이야기",
    "별개로",
    "뜬금",
    "아무튼",
    "by the way",
    "btw",
]


@dataclass(frozen=True)
class TopicResult:
    topic_relation: TopicRelation
    context_policy: ContextPolicy
    confidence: float
    reason: str
    state_overlap: float
    recent_overlap: float
    shift_marker_detected: bool


def detect_topic_relation(
    current_message: Message,
    recent_messages: list[Message],
    previous_state: ConversationState | None,
    options: BuildContextOptions,
) -> TopicResult:
    if not options.topic_shift_enabled:
        return TopicResult(
            topic_relation="continue_topic",
            context_policy="full_context",
            confidence=1.0,
            reason="topic shift detection disabled",
            state_overlap=1.0,
            recent_overlap=1.0,
            shift_marker_detected=False,
        )

    current_text = current_message.content
    current_terms = set(tokenize(current_text))
    if not current_terms:
        return TopicResult("ambiguous", "minimal_context", 0.5, "empty or non-tokenizable message", 0.0, 0.0, False)

    state_terms = _state_terms(previous_state)
    recent_terms = _recent_terms(recent_messages)
    state_overlap = _overlap(current_terms, state_terms)
    recent_overlap = _overlap(current_terms, recent_terms)
    max_overlap = max(state_overlap, recent_overlap)
    has_shift_marker = any(marker in current_text.lower() for marker in SHIFT_MARKERS)
    is_short = len(current_text.strip()) <= options.topic_ambiguous_short_message_chars

    if max_overlap >= options.topic_continue_threshold and not has_shift_marker:
        return TopicResult(
            "continue_topic",
            "full_context",
            round(min(0.95, 0.65 + max_overlap), 2),
            f"overlap {max_overlap:.2f} exceeded continue threshold",
            round(state_overlap, 3),
            round(recent_overlap, 3),
            has_shift_marker,
        )

    if max_overlap >= options.topic_related_threshold:
        return TopicResult(
            "related_topic",
            "focused_context",
            round(min(0.85, 0.5 + max_overlap), 2),
            f"overlap {max_overlap:.2f} exceeded related threshold",
            round(state_overlap, 3),
            round(recent_overlap, 3),
            has_shift_marker,
        )

    if has_shift_marker:
        return TopicResult(
            "new_topic",
            "fresh_context",
            0.86,
            "shift marker detected with low overlap",
            round(state_overlap, 3),
            round(recent_overlap, 3),
            has_shift_marker,
        )

    if is_short:
        return TopicResult(
            "ambiguous",
            "minimal_context",
            0.58,
            "short message with low overlap",
            round(state_overlap, 3),
            round(recent_overlap, 3),
            has_shift_marker,
        )

    return TopicResult(
        "new_topic",
        "fresh_context",
        0.78,
        "low overlap with previous conversation and state",
        round(state_overlap, 3),
        round(recent_overlap, 3),
        has_shift_marker,
    )


def prepare_inputs_for_policy(
    topic: TopicResult,
    recent_messages: list[Message],
    previous_state: ConversationState | None,
):
    if topic.context_policy == "full_context":
        return recent_messages, previous_state

    if topic.context_policy == "focused_context":
        return recent_messages, previous_state

    stripped_state = _strip_topic_specific_state(previous_state)
    if topic.context_policy == "minimal_context":
        return recent_messages[-2:], stripped_state

    return [], stripped_state


def filter_memories_for_policy(topic: TopicResult, memories):
    if topic.context_policy in {"full_context", "focused_context"}:
        return memories
    return [memory for memory in memories if memory.type == "user_preference"]


def _strip_topic_specific_state(previous_state: ConversationState | None) -> ConversationState | None:
    if not previous_state:
        return None
    state = previous_state.model_copy(deep=True)
    state.active_project = None
    state.current_focus = None
    state.user_goal = None
    return state


def _state_terms(state: ConversationState | None) -> set[str]:
    if not state:
        return set()
    parts = [
        state.active_project or "",
        state.current_focus or "",
        state.user_goal or "",
        " ".join(state.important_constraints),
        " ".join(state.decisions),
        " ".join(state.open_questions),
    ]
    return set(tokenize(" ".join(parts)))


def _recent_terms(messages: list[Message]) -> set[str]:
    return set(tokenize(" ".join(message.content for message in messages[-10:])))


def _overlap(current_terms: set[str], other_terms: set[str]) -> float:
    if not current_terms or not other_terms:
        return 0.0
    return len(current_terms & other_terms) / len(current_terms)

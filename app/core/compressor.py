from dataclasses import dataclass

from app.adapters.token_counter import estimate_tokens
from app.api.schemas import ConversationState, Memory
from app.core.intent import IntentResult
from app.core.retriever import ContextItem


@dataclass(frozen=True)
class CompressionResult:
    summary: str
    facts: list[str]
    constraints: list[str]
    decisions: list[str]
    open_questions: list[str]
    token_estimate: int


MAX_CONTENT_LENGTH: dict[str, int] = {
    "light": 320,
    "medium": 180,
    "aggressive": 100,
}

SECTION_CONTENT_LENGTH: dict[str, int] = {
    "light": 900,
    "medium": 520,
    "aggressive": 320,
}


def compress(
    context_items: list[ContextItem],
    state: ConversationState,
    intent: IntentResult,
    memories: list[Memory],
    level: str = "medium",
) -> CompressionResult:
    max_content_len = MAX_CONTENT_LENGTH.get(level, MAX_CONTENT_LENGTH["medium"])
    summary_parts: list[str] = []
    seen: set[str] = set()

    for item in context_items:
        if item.item_type == "document_section":
            compact = _compress_document_section(item, SECTION_CONTENT_LENGTH.get(level, 900))
        else:
            source_content = item.prompt_content or item.content
            compact = _compact(source_content, max_content_len)
        dedupe_key = compact[:80]
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        role = "User" if item.role == "user" else "Assistant" if item.role == "assistant" else "Document"
        summary_parts.append(f"- {role}: {compact}")

    summary = "\n".join(summary_parts) if summary_parts else "- No prior relevant context."

    constraints = list(state.important_constraints)
    decisions = list(state.decisions)
    open_questions = list(state.open_questions)
    facts: list[str] = []

    for memory in memories:
        if memory.type == "project_constraint":
            _append_unique(constraints, memory.content)
        elif memory.type == "decision":
            _append_unique(decisions, memory.content)
        elif memory.type == "unresolved_issue":
            _append_unique(open_questions, memory.content)
        elif memory.type == "fact":
            _append_unique(facts, memory.content)

    if intent.primary_intent == "coding":
        _append_unique(constraints, "UCE는 LLM을 내부에서 호출하지 않고 prompt_pack만 생성한다.")

    combined = "\n".join(summary_parts + constraints + decisions + open_questions + facts)
    return CompressionResult(
        summary=summary,
        facts=facts,
        constraints=constraints,
        decisions=decisions,
        open_questions=open_questions,
        token_estimate=estimate_tokens(combined),
    )


def _compact(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _compact_code(text: str, limit: int) -> str:
    compact = "\n".join(line.rstrip() for line in text.strip().splitlines())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _compress_document_section(item: ContextItem, limit: int) -> str:
    metadata = item.metadata or {}
    header_path = metadata.get("header_path") or metadata.get("section_title") or item.source
    query_words = set(metadata.get("query_words") or [])
    if metadata.get("content_type") == "code":
        body = _compact_code(item.content, limit)
    else:
        extracted = _extract_section_outline(item.content, query_words=query_words)
        body = _compact("\n".join(extracted), limit)
    return f"{header_path}\n{body}".strip()


def _extract_section_outline(text: str, query_words: set[str] | None = None) -> list[str]:
    lines = text.splitlines()
    focused = _extract_focused_heading_block(lines, query_words or set())
    if focused:
        return focused

    selected: list[str] = []
    pending_after_heading = 0
    in_code = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if not stripped:
            continue
        if stripped.startswith("#"):
            selected.append(stripped)
            pending_after_heading = 3
            continue
        if in_code:
            if pending_after_heading > 0 and len(stripped) <= 120:
                selected.append(stripped)
                pending_after_heading -= 1
            continue
        if pending_after_heading > 0:
            selected.append(stripped)
            pending_after_heading -= 1
            continue
        if stripped.startswith(("-", "*", "1.", "2.", "3.", "4.", "5.")):
            selected.append(stripped)
            continue
        if stripped.startswith("|") and not stripped.startswith("|---"):
            selected.append(stripped)
            continue
        if any(marker in stripped for marker in ["핵심 질문", "목표", "포함", "현재 목표", "Phase 2"]):
            selected.append(stripped)

    return selected or lines[:8]


def _extract_focused_heading_block(lines: list[str], query_words: set[str]) -> list[str]:
    phase_number = _requested_phase_number(query_words)
    if not phase_number:
        return []

    target = f"phase {phase_number}"
    parent_heading = ""
    focused: list[str] = []
    capture = False
    capture_level = 0

    for line in lines:
        stripped = line.strip()
        level = _markdown_heading_level(stripped)
        if level:
            if capture and level <= capture_level:
                break
            if not capture:
                parent_heading = stripped if level <= 2 else parent_heading
                if target in stripped.lower():
                    capture = True
                    capture_level = level
                    if parent_heading and parent_heading != stripped:
                        focused.append(parent_heading)
                    focused.append(stripped)
                continue
        elif capture and stripped:
            focused.append(stripped)

    return focused


def _requested_phase_number(query_words: set[str]) -> str | None:
    if "phase" not in query_words:
        return None
    for word in query_words:
        if str(word).isdigit():
            return str(word)
    return None


def _markdown_heading_level(stripped: str) -> int:
    if not stripped.startswith("#"):
        return 0
    level = len(stripped) - len(stripped.lstrip("#"))
    if 1 <= level <= 6 and stripped[level : level + 1] == " ":
        return level
    return 0


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)

from app.adapters.token_counter import estimate_tokens
from app.api.schemas import ConversationState, Message
from app.core.compressor import CompressionResult
from app.core.intent import IntentResult


PROMPT_TEMPLATE = """\
[System Role]
You are an assistant operating with a structured context pack.
Use the context below to answer the current user question.
Do not assume that unrelated omitted conversation exists.

[Current Goal]
{current_goal}

[Intent]
Primary intent: {primary_intent}
Secondary intents: {secondary_intents}
Reasoning mode: {reasoning_mode}

[Conversation State]
Active project: {active_project}
Current focus: {current_focus}

[Relevant Context]
{context_summary}

[Important Constraints]
{constraints}

[Key Decisions]
{decisions}

[Open Questions]
{open_questions}

[Relevant Facts]
{facts}

[Output Requirements]
- Answer in Korean unless the user asks otherwise.
- Be concrete and implementation-oriented.
- Preserve important constraints and decisions.
- If context is insufficient, state the gap clearly.

[Current User Question]
{current_message}
"""


def synthesize(
    current_message: Message,
    state: ConversationState,
    compressed: CompressionResult,
    intent: IntentResult,
    max_tokens: int,
) -> str:
    prompt = _render_prompt(current_message, state, compressed, intent, compressed.summary)
    if estimate_tokens(prompt) <= max_tokens:
        return prompt

    fixed_prompt = _render_prompt(current_message, state, compressed, intent, "")
    fixed_tokens = estimate_tokens(fixed_prompt)
    remaining_tokens = max(100, max_tokens - fixed_tokens)
    trimmed_summary = _trim_by_estimated_tokens(compressed.summary, remaining_tokens)
    return _render_prompt(current_message, state, compressed, intent, trimmed_summary + "\n- (context truncated by token budget)")


def _render_prompt(
    current_message: Message,
    state: ConversationState,
    compressed: CompressionResult,
    intent: IntentResult,
    context_summary: str,
) -> str:
    return PROMPT_TEMPLATE.format(
        current_goal=state.user_goal or state.current_focus or "현재 사용자 요청을 해결한다.",
        primary_intent=intent.primary_intent,
        secondary_intents=", ".join(intent.secondary_intents) or "none",
        reasoning_mode=intent.reasoning_mode,
        active_project=state.active_project or "unknown",
        current_focus=state.current_focus or "unknown",
        context_summary=context_summary or "- No prior relevant context.",
        constraints=_as_bullets(compressed.constraints),
        decisions=_as_bullets(compressed.decisions),
        open_questions=_as_bullets(compressed.open_questions),
        facts=_as_bullets(compressed.facts),
        current_message=current_message.content,
    )


def _as_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- none"


def _trim_by_estimated_tokens(text: str, token_budget: int) -> str:
    char_budget = max(120, token_budget * 2)
    if len(text) <= char_budget:
        return text
    return text[: char_budget - 3] + "..."

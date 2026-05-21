from app.adapters.token_counter import estimate_tokens
from app.api.schemas import ConversationState, Message
from app.core.compressor import CompressionResult
from app.core.intent import IntentResult


GROUNDING_INSTRUCTIONS: dict[str, str] = {
    "where": (
        "답변은 제공된 컨텍스트에만 근거해야 합니다.\n"
        "실행 위치, 배포 환경이 명시되지 않은 경우 '문서에 명시되지 않음'이라고 답하세요.\n"
        "클라우드, 서버, 인프라를 임의로 추정하지 마세요."
    ),
    "config": (
        "설정값은 컨텍스트에 명시된 것만 안내하세요. 기본값을 추정하지 마세요."
    ),
    "default": (
        "컨텍스트에 없는 사실을 추론하거나 가정하지 마세요.\n"
        "정보가 부족한 경우 '해당 내용은 제공된 문서에 없습니다'라고 답하세요."
    ),
}


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
{grounding_instructions}

[Current User Question]
{current_message}
"""


def synthesize(
    current_message: Message,
    state: ConversationState,
    compressed: CompressionResult,
    intent: IntentResult,
    max_tokens: int,
    query_type: str = "what",
) -> str:
    resolved_query_type = query_type
    if query_type == "what":
        resolved_query_type = getattr(intent, "query_type", query_type)
    prompt = _render_prompt(
        current_message,
        state,
        compressed,
        intent,
        compressed.summary,
        resolved_query_type,
    )
    if estimate_tokens(prompt) <= max_tokens:
        return prompt

    fixed_prompt = _render_prompt(current_message, state, compressed, intent, "", resolved_query_type)
    fixed_tokens = estimate_tokens(fixed_prompt)
    remaining_tokens = max(100, max_tokens - fixed_tokens)
    trimmed_summary = _trim_by_estimated_tokens(compressed.summary, remaining_tokens)
    return _render_prompt(
        current_message,
        state,
        compressed,
        intent,
        trimmed_summary + "\n- (context truncated by token budget)",
        resolved_query_type,
    )


def _render_prompt(
    current_message: Message,
    state: ConversationState,
    compressed: CompressionResult,
    intent: IntentResult,
    context_summary: str,
    query_type: str,
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
        grounding_instructions=_grounding_instructions(query_type),
        current_message=current_message.content,
    )


def _as_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- none"


def _grounding_instructions(query_type: str) -> str:
    instructions = GROUNDING_INSTRUCTIONS.get(query_type, GROUNDING_INSTRUCTIONS["default"])
    return "\n".join(f"- {line}" for line in instructions.splitlines())


def _trim_by_estimated_tokens(text: str, token_budget: int) -> str:
    char_budget = max(120, token_budget * 2)
    if len(text) <= char_budget:
        return text
    return text[: char_budget - 3] + "..."

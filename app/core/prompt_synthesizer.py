from app.adapters.token_counter import estimate_tokens
from app.api.schemas import ConversationState, Message
from app.core.compressor import CompressionResult
from app.core.grounding_policy import GroundingPolicy
from app.core.intent import IntentResult


_REQUIREMENTS: dict[GroundingPolicy, str] = {
    GroundingPolicy.GENERAL: (
        "- Answer in Korean unless the user asks otherwise.\n"
        "- Be natural and conversational.\n"
        "- You may use general knowledge when no relevant context exists.\n"
        "- If context is insufficient, continue the conversation naturally."
    ),
    GroundingPolicy.DOCUMENT_GROUNDED: (
        "- Answer in Korean unless the user asks otherwise.\n"
        "- Base the answer primarily on the provided context.\n"
        "- Do not invent facts not supported by the retrieved documents.\n"
        "- If information is missing, explicitly state that the document does not contain it."
    ),
    GroundingPolicy.XDR_ANALYSIS: (
        "- Answer in Korean unless the user asks otherwise.\n"
        "- Base the answer only on the provided xDR dataset results.\n"
        "- Do not assume facts not present in the query result.\n"
        "- Use markdown tables when presenting structured xDR results.\n"
        "- Preserve identifiers such as IMSI, IMEI, MME_ID exactly as provided."
    ),
    GroundingPolicy.HYBRID: (
        "- Answer in Korean unless the user asks otherwise.\n"
        "- Use xDR dataset results as the primary source.\n"
        "- Supplement with document context where relevant.\n"
        "- Do not assume facts not present in the provided data.\n"
        "- Use markdown tables when presenting structured xDR results."
    ),
}


def build_output_requirements(policy: GroundingPolicy, query_type: str = "what") -> str:
    """Build Output Requirements section from GroundingPolicy.

    query_type is accepted for interface compatibility but no longer drives
    strict-grounding rule selection — policy is the sole authority.
    GENERAL never includes strict grounding rules.
    """
    return _REQUIREMENTS.get(policy, _REQUIREMENTS[GroundingPolicy.GENERAL])


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
{output_requirements}

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
    policy: GroundingPolicy | None = None,
) -> str:
    resolved_query_type = query_type
    if query_type == "what":
        resolved_query_type = getattr(intent, "query_type", query_type)
    resolved_policy = policy if policy is not None else GroundingPolicy.GENERAL
    prompt = _render_prompt(
        current_message,
        state,
        compressed,
        intent,
        compressed.summary,
        resolved_query_type,
        resolved_policy,
    )
    if estimate_tokens(prompt) <= max_tokens:
        return prompt

    fixed_prompt = _render_prompt(
        current_message, state, compressed, intent, "", resolved_query_type, resolved_policy
    )
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
        resolved_policy,
    )


def _render_prompt(
    current_message: Message,
    state: ConversationState,
    compressed: CompressionResult,
    intent: IntentResult,
    context_summary: str,
    query_type: str,
    policy: GroundingPolicy,
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
        output_requirements=build_output_requirements(policy, query_type),
        current_message=current_message.content,
    )


def _as_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- none"


def _trim_by_estimated_tokens(text: str, token_budget: int) -> str:
    char_budget = max(120, token_budget * 2)
    if len(text) <= char_budget:
        return text
    kept_lines: list[str] = []
    used_chars = 0
    for line in text.splitlines():
        line_cost = len(line) + 1
        if used_chars + line_cost > char_budget:
            continue
        kept_lines.append(line)
        used_chars += line_cost
    if not kept_lines:
        return "- (context omitted by token budget)"
    kept_lines.append("- (lower-ranked context omitted by token budget)")
    return "\n".join(kept_lines)

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    id: str | None = None
    role: Literal["user", "assistant", "system"] = "user"
    content: str = ""
    created_at: datetime | None = None


class Memory(BaseModel):
    id: str | None = None
    type: Literal[
        "user_preference",
        "project_constraint",
        "decision",
        "fact",
        "unresolved_issue",
    ]
    content: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    created_at: datetime | None = None


class DocumentInput(BaseModel):
    id: str | None = None
    title: str | None = None
    content: str
    content_type: Literal["markdown", "text", "code", "json", "yaml", "log", "docx", "xlsx", "dpe_ir"] = "text"
    source: str | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class ConversationState(BaseModel):
    active_project: str | None = None
    current_focus: str | None = None
    user_goal: str | None = None
    important_constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    reasoning_mode: str | None = None


class BuildContextOptions(BaseModel):
    max_prompt_tokens: int = Field(default=4000, ge=800)
    target_model: str = "generic"
    compression_level: Literal["light", "medium", "aggressive"] = "medium"
    include_trace: bool = True
    max_recent_messages: int = Field(default=15, ge=1, le=100)
    topic_shift_enabled: bool = True
    topic_continue_threshold: float = Field(default=0.18, ge=0.0, le=1.0)
    topic_related_threshold: float = Field(default=0.08, ge=0.0, le=1.0)
    topic_ambiguous_short_message_chars: int = Field(default=12, ge=1)
    structure_chunking_enabled: bool = True
    chunk_max_chars: int = Field(default=1400, ge=300, le=8000)
    chunk_overlap_chars: int = Field(default=120, ge=0, le=1000)
    survival_metadata_limit: int = Field(default=20, ge=0, le=100)


class BuildContextRequest(BaseModel):
    session_id: str
    current_message: Message | None = None
    recent_messages: list[Message] = Field(default_factory=list)
    previous_state: ConversationState | None = None
    optional_memories: list[Memory] = Field(default_factory=list)
    documents: list[DocumentInput] = Field(default_factory=list)
    options: BuildContextOptions = Field(default_factory=BuildContextOptions)


class CompressedContext(BaseModel):
    summary: str
    facts: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    token_estimate: int = 0


class PromptPack(BaseModel):
    format: Literal["structured_text"] = "structured_text"
    content: str
    estimated_tokens: int
    original_tokens: int


class BuildContextMetadata(BaseModel):
    trace_id: str
    primary_intent: str
    secondary_intents: list[str] = Field(default_factory=list)
    intent_confidence: float
    query_type: str = "what"
    compression_level: str = "medium"
    topic_relation: str
    context_policy: str
    topic_confidence: float
    topic_reason: str
    selected_context_count: int
    dropped_context_count: int
    retrieval_confidence: float
    retrieval_warning: str | None = None
    compression_ratio: float
    prompt_build_latency_ms: int
    provider_profile: str
    survived_items: list[dict[str, Any]] = Field(default_factory=list)
    dropped_items: list[dict[str, Any]] = Field(default_factory=list)
    survival_reasons: dict[str, str] = Field(default_factory=dict)


class BuildContextResponse(BaseModel):
    session_id: str
    conversation_state: ConversationState
    compressed_context: CompressedContext
    prompt_pack: PromptPack
    metadata: BuildContextMetadata


class AnalyzeResponseOptions(BaseModel):
    extract_memory_candidates: bool = True
    extract_open_questions: bool = True
    topic_relation: str | None = None
    context_policy: str | None = None


class AnalyzeResponseRequest(BaseModel):
    session_id: str
    current_message: Message
    assistant_response: Message
    conversation_state: ConversationState
    options: AnalyzeResponseOptions = Field(default_factory=AnalyzeResponseOptions)


class MemoryCandidate(BaseModel):
    type: Literal[
        "user_preference",
        "project_constraint",
        "decision",
        "fact",
        "unresolved_issue",
    ]
    content: str
    importance: float = Field(ge=0.0, le=1.0)
    stability: Literal["session", "long_term"] = "session"
    source: str = "assistant_response"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class AnalyzeResponseResponse(BaseModel):
    next_state_patch: dict[str, Any] = Field(default_factory=dict)
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    version: str
    components: dict[str, str]


class StatusResponse(BaseModel):
    compression_level: str
    intent_mode: str
    target_model_note: str
    active_provider_profiles: list[str]
    uptime_seconds: int

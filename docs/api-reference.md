# UCE API Reference
> Version: 0.3  
> Last Updated: 2026-05-20

Base URL: `http://localhost:8100`

---

## POST /build-context

현재 메시지, 최근 대화, 선택적 메모리, 문서를 받아 LLM에 전달할 `Context Pack`을 생성한다.

UCE는 LLM을 호출하지 않는다. 응답의 `prompt_pack.content`를 application이 기존 LLM entrypoint로 전달한다.

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | ✅ | 세션 식별자 |
| `current_message` | Message \| null | ❌ | 현재 사용자 메시지. 없거나 빈 문자열이면 queryless document compression mode |
| `recent_messages` | Message[] | ❌ | 최근 대화 목록 |
| `previous_state` | State \| null | ❌ | 이전 턴에서 받은 conversation_state |
| `optional_memories` | Memory[] | ❌ | 외부 application이 전달하는 메모리 |
| `documents` | Document[] | ❌ | 매 요청에 함께 전달하는 문서 |
| `options` | Options | ❌ | 동작 옵션 |

### Message

```json
{
  "id": "msg_001",
  "role": "user",
  "content": "UCE가 뭔지 설명해줘.",
  "created_at": "2026-05-20T10:00:00+09:00"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ❌ | 메시지 식별자 |
| `role` | `user | assistant | system` | ❌ | 기본값 `user` |
| `content` | string | ❌ | 기본값 `""` |
| `created_at` | string | ❌ | ISO 8601 |

### Document

```json
{
  "id": "doc_1",
  "title": "UCE Architecture",
  "content": "# UCE Architecture...",
  "content_type": "markdown",
  "source": "docs/architecture.md",
  "importance": 0.85
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ❌ | 문서 식별자 |
| `title` | string | ❌ | 문서 제목 |
| `content` | string | ✅ | 문서 내용. API는 파일 경로가 아니라 이미 읽힌 text를 받는다 |
| `content_type` | string | ❌ | `markdown`, `text`, `code`, `json`, `yaml`, `log`, `docx`, `xlsx` |
| `source` | string | ❌ | 원본 출처 |
| `importance` | float | ❌ | application 제공 중요도. 기본 0.5 |

HTTP API는 file upload API가 아니다. `.docx`, `.xlsx` 파일은 application 또는 UCE CLI adapter가 markdown/text로 변환한 뒤 `content`에 넣어 전달한다. UCE repo는 개발 편의를 위해 `app/adapters/document_loader.py`의 `load_docx`, `load_xlsx`를 제공한다.

### Memory

```json
{
  "id": "mem_001",
  "type": "project_constraint",
  "content": "UCE는 stateless middleware이다.",
  "importance": 0.9,
  "confidence": 0.8,
  "created_at": "2026-05-20T09:00:00+09:00"
}
```

UCE는 memory를 저장하지 않는다. application이 전달한 memory를 읽고 prompt assembly에 반영할 뿐이다.

### Options

```json
{
  "max_prompt_tokens": 4000,
  "target_model": "ollama:exaone3.5:7.8b",
  "compression_level": "medium",
  "include_trace": true,
  "max_recent_messages": 15,
  "topic_shift_enabled": true,
  "structure_chunking_enabled": true,
  "chunk_max_chars": 1400,
  "chunk_overlap_chars": 120,
  "survival_metadata_limit": 20
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_prompt_tokens` | int | 4000 | 최대 prompt token 목표 |
| `target_model` | string | `generic` | provider profile 선택 힌트 |
| `compression_level` | `light | medium | aggressive` | `medium` | 압축 강도 |
| `include_trace` | bool | true | trace/debug metadata 포함 |
| `max_recent_messages` | int | 15 | 최근 대화 최대 사용 개수 |
| `topic_shift_enabled` | bool | true | topic shift detector 사용 |
| `topic_continue_threshold` | float | 0.18 | continue 판정 threshold |
| `topic_related_threshold` | float | 0.08 | related 판정 threshold |
| `topic_ambiguous_short_message_chars` | int | 12 | 짧은 메시지 ambiguous 처리 기준 |
| `structure_chunking_enabled` | bool | true | document structure parsing 사용 |
| `chunk_max_chars` | int | 1400 | 긴 section 내부 compression 기준 |
| `chunk_overlap_chars` | int | 120 | 긴 chunk 분할 시 overlap |
| `survival_metadata_limit` | int | 20 | selected/dropped debug metadata 최대 개수 |

### Queryless Mode

`current_message`가 없거나 `content`가 빈 문자열이면 UCE는 질문 없이 문서 전체를 중요도 순으로 압축한다.

동작:

- intent는 `summarize`
- topic policy는 `fresh_context`
- recent message retrieval은 생략
- document sections를 중요도 순으로 ranking
- min score 제한 없이 document candidates를 선택

예시:

```json
{
  "session_id": "doc_summary_001",
  "documents": [
    {
      "title": "UCE Architecture",
      "content": "# UCE Architecture...",
      "content_type": "markdown"
    }
  ]
}
```

### Response Body

```json
{
  "session_id": "test_session_001",
  "conversation_state": {
    "active_project": "UCE",
    "current_focus": "architecture design",
    "user_goal": "UCE Phase 2 목표 설명",
    "important_constraints": [],
    "open_questions": [],
    "decisions": [],
    "reasoning_mode": "explanation"
  },
  "compressed_context": {
    "summary": "- Document: ...",
    "facts": [],
    "constraints": [],
    "decisions": [],
    "open_questions": [],
    "token_estimate": 377
  },
  "prompt_pack": {
    "format": "structured_text",
    "content": "[System Role]\n...",
    "estimated_tokens": 377,
    "original_tokens": 911
  },
  "metadata": {
    "trace_id": "trace_abc123",
    "primary_intent": "explain",
    "secondary_intents": [],
    "intent_confidence": 0.95,
    "topic_relation": "new_topic",
    "context_policy": "fresh_context",
    "topic_confidence": 0.78,
    "topic_reason": "low overlap with previous conversation and state",
    "selected_context_count": 1,
    "dropped_context_count": 0,
    "retrieval_confidence": 0.74,
    "retrieval_warning": null,
    "compression_ratio": 0.17,
    "prompt_build_latency_ms": 13,
    "provider_profile": "ollama_exaone_7b",
    "survived_items": [],
    "dropped_items": [],
    "survival_reasons": {}
  }
}
```

`survived_items`와 `dropped_items`에는 explainable retrieval을 위한 score breakdown이 들어간다.

주요 score:

- `semantic_score`
- `heading_score`
- `section_path_score`
- `section_priority_score`
- `section_coherence_score`
- `recency_score`
- `intent_alignment_score`
- `constraint_score`
- `decision_score`
- `mismatch_penalty`
- `final_score`

`retrieval_warning`은 관련 context를 충분히 찾지 못했을 때 `no_context_selected` 또는 `low_relevance_context`가 된다.

---

## POST /analyze-response

LLM 응답을 분석하여 다음 state patch와 memory candidates를 반환한다.

UCE는 저장하지 않는다. application이 반환값을 저장할지 결정한다.

### Request Body

```json
{
  "session_id": "test_session_001",
  "current_message": {
    "role": "user",
    "content": "UCE가 뭔지 설명해줘."
  },
  "assistant_response": {
    "role": "assistant",
    "content": "UCE는 LLM 앞단에서..."
  },
  "conversation_state": {
    "active_project": "UCE",
    "current_focus": "architecture design"
  },
  "options": {
    "extract_memory_candidates": true,
    "extract_open_questions": true,
    "topic_relation": "continue_topic",
    "context_policy": "full_context"
  }
}
```

### Response Body

```json
{
  "next_state_patch": {
    "current_focus": "MVP implementation planning",
    "decisions": ["POST /build-context를 1차 MVP API로 확정"]
  },
  "memory_candidates": [
    {
      "type": "project_constraint",
      "content": "UCE는 stateless이며 memory storage를 소유하지 않는다.",
      "importance": 0.88,
      "stability": "long_term",
      "source": "assistant_response",
      "confidence": 0.91
    }
  ],
  "unresolved_issues": [],
  "metadata": {
    "semantic_importance": 0.78
  }
}
```

---

## GET /health

```json
{
  "status": "ok",
  "version": "0.1.0",
  "components": {
    "intent_analyzer": "ok",
    "retriever": "ok",
    "compressor": "ok",
    "prompt_synthesizer": "ok"
  }
}
```

---

## GET /status

```json
{
  "compression_level": "medium",
  "intent_mode": "rule_based",
  "target_model_note": "EXAONE 3.5 7.8b is the first target profile, not a model limit.",
  "active_provider_profiles": [
    "generic",
    "ollama_exaone_7b",
    "ollama_qwen",
    "ollama_gemma",
    "cloud_large"
  ],
  "uptime_seconds": 3842
}
```

---

## Error Behavior

FastAPI validation error는 기본 `422` 응답을 반환한다.

Integration 측에서는 UCE 실패를 반드시 legacy prompt flow로 fallback해야 한다.

Fallback 대상:

- UCE unavailable
- timeout
- invalid response
- HTTP 5xx
- unexpected exception

---

## Provider Profiles

| target model hint | Profile |
|-------------------|---------|
| `exaone`, `exaone3.5`, `ollama:exaone3.5:7.8b` | `ollama_exaone_7b` |
| `qwen` | `ollama_qwen` |
| `gemma` | `ollama_gemma` |
| cloud/large model hints | `cloud_large` |
| default | `generic` |


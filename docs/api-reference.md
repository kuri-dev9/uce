# UCE API Reference
> Version: 0.1  
> Last Updated: 2026-05-19

Base URL: `http://localhost:8100`

---

## POST /build-context

현재 사용자 메시지와 최근 대화, 선택적 메모리를 받아 LLM에 전달할 Context Pack을 생성한다.

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | ✅ | 세션 식별자 |
| `current_message` | Message | ✅ | 현재 사용자 메시지 |
| `recent_messages` | Message[] | ✅ | 최근 대화 목록 (비어 있어도 됨) |
| `previous_state` | State \| null | ❌ | 이전 턴에서 받은 conversation_state |
| `optional_memories` | Memory[] | ❌ | 외부에서 전달하는 메모리 목록 |
| `documents` | Document[] | ❌ | 매 요청에 함께 전달하는 normalized text/markdown 문서. UCE는 저장하지 않음 |
| `options` | Options | ❌ | 동작 옵션 |

#### Message

```json
{
  "id": "msg_001",
  "role": "user | assistant",
  "content": "메시지 내용",
  "created_at": "2026-05-19T10:00:00+09:00"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ❌ | 메시지 식별자 |
| `role` | string | ✅ | `user` 또는 `assistant` |
| `content` | string | ✅ | 메시지 본문 |
| `created_at` | string (ISO 8601) | ❌ | 생성 시각 |

#### Memory

```json
{
  "id": "mem_001",
  "type": "project_constraint | decision | fact | user_preference | unresolved_issue",
  "content": "UCE는 stateless middleware이다.",
  "importance": 0.9,
  "created_at": "2026-05-19T09:00:00+09:00"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ❌ | 메모리 식별자 |
| `type` | string | ✅ | 메모리 종류 |
| `content` | string | ✅ | 메모리 내용 |
| `importance` | float (0.0~1.0) | ❌ | 중요도. 기본값 0.5 |
| `created_at` | string (ISO 8601) | ❌ | 생성 시각 |

#### Options

```json
{
  "max_prompt_tokens": 4000,
  "target_model": "ollama:exaone3.5:7.8b",
  "compression_level": "medium",
  "include_trace": true,
  "structure_chunking_enabled": true,
  "chunk_max_chars": 1400,
  "chunk_overlap_chars": 120,
  "survival_metadata_limit": 20
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_prompt_tokens` | int | 4000 | 최대 prompt token 수 |
| `target_model` | string | `"generic"` | 대상 모델. provider profile 결정에 사용 |
| `compression_level` | string | `"medium"` | `light` \| `medium` \| `aggressive` |
| `include_trace` | bool | true | metadata에 trace 포함 여부 |
| `structure_chunking_enabled` | bool | true | documents 입력에 structure-aware chunking 적용 |
| `chunk_max_chars` | int | 1400 | document chunk 최대 글자 수 |
| `chunk_overlap_chars` | int | 120 | 긴 chunk 분할 시 overlap |
| `survival_metadata_limit` | int | 20 | survived/dropped metadata 최대 개수 |

#### Document

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

`documents`는 매 요청 입력이다. UCE는 문서를 저장하지 않으며, 파일 파싱도 담당하지 않는다. application이 docx/pdf/xlsx 등을 text 또는 markdown으로 변환한 뒤 전달한다.

### Response Body

```json
{
  "session_id": "test_session_001",
  "conversation_state": {
    "active_project": "UCE",
    "current_focus": "architecture design",
    "user_goal": "Local LLM 앞에 UCE 붙이기",
    "important_constraints": [
      "UCE는 stateless middleware",
      "memory를 직접 소유하지 않음"
    ],
    "open_questions": [],
    "decisions": [
      "Python + FastAPI 사용",
      "EXAONE 3.5 7.8b가 1차 타겟"
    ],
    "reasoning_mode": "technical_design"
  },
  "compressed_context": {
    "summary": "User is building UCE...",
    "facts": [],
    "constraints": ["UCE는 stateless middleware"],
    "decisions": ["Python + FastAPI 사용"],
    "open_questions": [],
    "token_estimate": 320
  },
  "prompt_pack": {
    "format": "structured_text",
    "content": "[Current Goal]\n...\n[Current User Question]\n...",
    "estimated_tokens": 2800,
    "original_tokens": 8400
  },
  "metadata": {
    "trace_id": "trace_abc123",
    "primary_intent": "design",
    "intent_confidence": 0.87,
    "selected_context_count": 6,
    "dropped_context_count": 11,
    "retrieval_confidence": 0.74,
    "retrieval_warning": null,
    "compression_ratio": 0.33,
    "prompt_build_latency_ms": 38,
    "survived_items": [],
    "dropped_items": [],
    "survival_reasons": {}
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | 요청한 세션 식별자 |
| `conversation_state` | State | 현재 턴에서 생성된 state. 다음 턴 previous_state로 사용 |
| `compressed_context` | CompressedContext | 압축된 context 구조 |
| `prompt_pack` | PromptPack | LLM에 전달할 최종 prompt |
| `metadata` | Metadata | 처리 통계 및 trace 정보 |

`retrieval_confidence`는 선택된 상위 context의 평균 score이다. 값이 낮으면 `retrieval_warning`에 `no_context_selected` 또는 `low_relevance_context`가 들어간다. 이 값은 "문서에 정보가 없다"와 "retriever가 관련 chunk를 제대로 못 찾았다"를 구분하기 위한 debugging signal이다.

#### PromptPack

| Field | Type | Description |
|-------|------|-------------|
| `format` | string | 항상 `"structured_text"` |
| `content` | string | LLM에 전달할 prompt 전문 |
| `estimated_tokens` | int | 생성된 prompt의 예상 token 수 |
| `original_tokens` | int | 압축 전 원본 context의 token 수 |

---

## POST /analyze-response

LLM 응답을 분석하여 다음 state patch와 memory candidates를 반환한다.

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
    "extract_open_questions": true
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | ✅ | 세션 식별자 |
| `current_message` | Message | ✅ | 사용자 메시지 |
| `assistant_response` | Message | ✅ | LLM 응답 |
| `conversation_state` | State | ✅ | 현재 conversation_state |
| `options.extract_memory_candidates` | bool | ❌ | memory 후보 추출 여부. 기본 true |
| `options.extract_open_questions` | bool | ❌ | 미결 질문 추출 여부. 기본 true |

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
  "unresolved_issues": [
    "Storage adapter interface가 아직 확정되지 않음"
  ],
  "metadata": {
    "semantic_importance": 0.78
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `next_state_patch` | object | 다음 턴 state에 병합할 patch |
| `memory_candidates` | MemoryCandidate[] | 저장 제안 목록. 저장 여부는 application이 결정 |
| `unresolved_issues` | string[] | 미결 사항 목록 |
| `metadata.semantic_importance` | float | 응답의 의미적 중요도 (0.0~1.0) |

#### MemoryCandidate

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | `user_preference \| project_constraint \| decision \| fact \| unresolved_issue` |
| `content` | string | 저장 후보 내용 |
| `importance` | float | 중요도 (0.0~1.0) |
| `stability` | string | `session \| long_term` |
| `source` | string | 출처 |
| `confidence` | float | 추출 신뢰도 (0.0~1.0) |

---

## GET /health

서비스 상태 확인.

### Response

```json
{
  "status": "ok",
  "version": "0.1.0",
  "components": {
    "intent_analyzer": "ok",
    "compressor": "ok",
    "prompt_synthesizer": "ok"
  }
}
```

---

## GET /status

런타임 상태 확인.

### Response

```json
{
  "compression_level": "medium",
  "intent_mode": "rule_based",
  "active_provider_profiles": ["ollama_exaone", "generic"],
  "uptime_seconds": 3842
}
```

---

## Error Responses

모든 API는 오류 시 다음 형식으로 응답한다.

```json
{
  "error": "validation_error",
  "message": "current_message.role must be 'user' or 'assistant'",
  "trace_id": "trace_abc123"
}
```

| HTTP Status | Error Type | Description |
|-------------|------------|-------------|
| 400 | `validation_error` | 요청 스키마 오류 |
| 422 | `unprocessable_entity` | 필드 값 오류 |
| 500 | `internal_error` | 서버 내부 오류 |

---

## Provider Profile 목록

`options.target_model`에 따라 자동으로 provider profile이 선택된다.

| target_model | Profile | max_tokens | compression |
|--------------|---------|-----------|-------------|
| `ollama:exaone3.5:7.8b` | `ollama_exaone_7b` | 4000 | medium |
| `ollama:qwen*` | `ollama_qwen` | 4000 | medium |
| `ollama:gemma*` | `ollama_gemma` | 4000 | medium |
| `openai:gpt-4*` | `openai_gpt4` | 8000 | light |
| `anthropic:claude*` | `anthropic_claude` | 8000 | light |
| `generic` | `generic` | 4000 | medium |

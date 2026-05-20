# UCE Roadmap
> Version: 0.3  
> Last Updated: 2026-05-20

---

## Current Position

UCE는 Phase 1 MVP와 Phase 2 Practical Context Engineering 구현을 완료했다.

현재 UCE는 다음 상태로 동작한다.

- stateless HTTP middleware
- provider-agnostic Context Pack generator
- local LLM 검증용 raw vs UCE 비교 도구 보유
- markdown/text/code/docx/xlsx 입력을 normalized context로 처리
- section-level retrieval + local compression 기반 prompt assembly
- reasondock에 optional middleware로 통합되어 실제 채팅 흐름에서 검증 가능

1차 검증 모델은 **EXAONE 3.5 7.8B via Ollama**이다. 단, 이는 첫 target profile일 뿐 모델 제한이 아니다.

---

## Phase 1 — Context Pack MVP

**목표**: UCE가 LLM 앞단에서 prompt pack을 생성하는 독립 middleware로 동작하는지 검증한다.

| 항목 | 설명 | 상태 |
|------|------|------|
| `POST /build-context` | context pack 생성 API | ✅ 완료 |
| `POST /analyze-response` | 응답 분석 및 state patch 후보 생성 | ✅ 완료 |
| `GET /health`, `GET /status` | 상태 확인 API | ✅ 완료 |
| Intent Analyzer | rule-based intent 분류 | ✅ 완료 |
| Conversation State Builder | active project/focus/goal/constraints/decisions 구성 | ✅ 완료 |
| Recent Context Retriever | 최근 대화 기반 context 후보 선택 | ✅ 완료 |
| Topic Shift Detector | continue/related/ambiguous/new_topic policy 결정 | ✅ 완료 |
| Semantic Compressor | constraints/decisions/facts 중심 압축 | ✅ 완료 |
| Prompt Synthesizer | structured prompt pack 생성 | ✅ 완료 |
| Provider Profiles | generic, EXAONE, Qwen, Gemma, cloud_large profile | ✅ 완료 |
| Docker Runtime | Dockerfile + graceful shutdown server | ✅ 완료 |

Phase 1의 핵심 결론:

```text
UCE는 LLM을 호출하지 않아도, 기존 backend가 바로 사용할 수 있는 prompt_pack을 생성할 수 있다.
```

---

## Phase 2 — Practical Context Engineering

**목표**: 실제 문서/대화/코드 입력에서 retrieval 품질을 개선하고, raw prompt 대비 UCE prompt pack이 실용적 이점을 주는지 검증한다.

| 항목 | 설명 | 상태 |
|------|------|------|
| Content-Type Aware Processing | markdown / text / code / json / yaml / log / docx / xlsx 처리 경로 | ✅ 완료 |
| Structure-Preserving Chunking | markdown heading tree, code symbol block 기반 분할 | ✅ 완료 |
| Section-Level Retrieval | small chunk first 대신 large semantic block first | ✅ 완료 |
| Heading-Aware Scoring | heading, section path, exact heading priority 반영 | ✅ 완료 |
| Context Importance Scoring | semantic, heading, coherence, intent, constraint, recency 기반 scoring | ✅ 완료 |
| Explainable Retrieval Metadata | selected/dropped item, score breakdown, selected_reason | ✅ 완료 |
| Adaptive Compression | intent별 보존 항목 조정 | ✅ 완료 |
| Code Compression Guard | 코드 입력은 aggressive outline 압축을 피하고 구조 보존 | ✅ 완료 |
| Table/Code Fence Handling | markdown table과 code fence 내용 소실 방지 | ✅ 완료 |
| `current_message` Optional | query 없이 전체 문서를 중요도 순으로 압축하는 모드 | ✅ 완료 |
| `document_loader` | python-docx/openpyxl 기반 docx/xlsx → markdown 변환 | ✅ 완료 |
| Scenario Fixtures | ghost constraint, reasoning drift, context junk, Phase 2 heading retrieval | ✅ 완료 |
| `scripts/compare-ollama.py` | raw vs UCE EXAONE 비교 runner | ✅ 완료 |
| `scripts/try-uce.py` | 임의 입력/문서로 prompt pack과 LLM 응답 확인 | ✅ 완료 |
| reasondock Integration | optional UCE middleware, fallback, metrics, debug panel | ✅ 완료 |

Phase 2의 핵심 결론:

```text
retrieve large → compress locally
```

문서 retrieval은 paragraph 단위 조각이 아니라 H1/H2/H3 및 code symbol 같은 semantic block을 먼저 선택한다. token reduction은 선택된 section 내부에서 수행한다.

---

## Phase 2 Validation Result

reasondock 통합 후 실제 채팅 흐름에서 다음 비교가 확인되었다.

| 항목 | Legacy | UCE |
|------|--------|-----|
| `use_uce` | false | true |
| `fallback_used` | false | false |
| `original_prompt_tokens` | 829 | 911 |
| `final_prompt_tokens` | 829 | 377 |
| `compression_ratio` | 1.0 | 0.17 |
| `llm_first_token_ms` | 43136 | 28136 |
| `llm_total_latency_ms` | 73821 | 43392 |
| `selected_context_count` | 0 | 1 |
| `intent` | `-` | `explain` |
| `topic_relation` | `-` | `new_topic` |

이 결과는 benchmark가 아니라 practical validation이다. 의미 있는 점은 다음이다.

- UCE가 문서에서 관련 context만 선별했다.
- prompt token이 크게 줄었다.
- first token latency와 total latency가 감소했다.
- fallback 없이 기존 LLM entrypoint를 유지했다.
- legacy flow는 UCE 없이 계속 동작했다.

---

## Phase 2 Known Limits

현재 의도적으로 남겨둔 한계:

- xlsx는 Phase 2에서 sheet 전체를 markdown table로 전달한다.
- 수치 집계/count/filter 정확도는 LLM에게 맡기지 않는 것이 바람직하다.
- PDF/OCR은 아직 core scope가 아니다.
- persistent memory store는 제공하지 않는다.
- vector DB나 embedding-first retrieval은 도입하지 않았다.
- automatic benchmark scoring은 아직 없다. 현재는 scenario runner + manual review 중심이다.

---

## Phase 3 — Type-Aware Preprocessing Runtime

**목표**: 문서 타입별 전용 adapter를 도입하여 UCE를 더 안정적인 preprocessing runtime으로 확장한다.

Phase 3 후보:

| 항목 | 설명 |
|------|------|
| SpreadsheetAdapter | xlsx/csv를 raw context가 아니라 QueryPlan + deterministic execution으로 처리 |
| LogAdapter | timestamp grouping, trace chain, error event extraction |
| CodeAdapter 고도화 | AST-lite symbol indexing, call relation, dependency context |
| Adaptive Compression 고도화 | intent + model profile + document type 기반 동적 압축 |
| Evaluation Report Generator | scenario 결과를 누적하고 human score와 metadata 비교 |
| Prompt Leak Guard 고도화 | debug/prompt context가 사용자 응답에 노출되지 않도록 추가 방어 |

### SpreadsheetAdapter 방향

Phase 3에서 xlsx/csv는 semantic document가 아니라 임시 데이터 테이블로 취급한다.

```text
자연어 질문
  -> RuleBasedPlanner 또는 LLM Planner(QueryPlan만 생성)
  -> DataFrameExecutor가 deterministic 실행
  -> facts[] 생성
  -> LLM은 계산 결과 설명만 담당
```

LLM이 pandas 코드를 직접 생성하거나 실행하지 않는다.

---

## Next Work

우선순위는 다음과 같다.

1. NewSpeed 통합 검증
2. reasondock UCE debug metrics 개선
3. scenario 결과 리포트 포맷 정리
4. xlsx/csv SpreadsheetAdapter 설계 확정
5. 코드/로그 adapter 고도화 범위 결정

---

## Long-Term Direction

UCE가 지켜야 할 원칙:

```text
Own the assembly.
Do not own the world.
```

UCE는 다음이 되지 않는다.

- Memory platform
- Autonomous agent framework
- Full RAG system
- Vector DB platform
- LLM provider

UCE가 될 것:

- 모든 LLM application 앞단에 붙을 수 있는 context preparation layer
- local LLM과 cloud LLM 모두에서 대화 연속성, token efficiency, prompt quality를 개선하는 middleware


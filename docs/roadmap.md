# UCE Roadmap
> Version: 0.2
> Last Updated: 2026-05-20

---

## 현재 위치

UCE v0.2는 Phase 1 MVP 구현을 완료하고 Phase 2 실전 검증을 진행 중이다.

1차 타겟: **EXAONE 3.5 7.8b (Ollama)** + **한국어 대화**
이식 대상: **reasondock** (대화형 채팅 앱), **NewSpeed** (뉴스 이벤트 파이프라인)

---

## Phase 1 — Context Pack MVP

**목표**: UCE의 핵심 가치를 가장 작게 검증한다.

**완료 기준**:
- `/build-context` 응답만으로 LLM 호출 prompt를 만들 수 있다
- 최근 대화가 길어져도 핵심 목표/제약이 prompt에 유지된다
- EXAONE 3.5에서 반복 설명 없이 대화가 이어진다
- token 사용량이 원본 대비 의미 있게 감소한다

**구현 항목**:

| 항목 | 설명 | 상태 |
|------|------|------|
| `POST /build-context` | Core API | 🔲 구현 예정 |
| `POST /analyze-response` | 응답 분석 API | 🔲 구현 예정 |
| `GET /health`, `GET /status` | 상태 확인 API | 🔲 구현 예정 |
| Intent Analyzer (rule-based) | keyword 기반 분류 | 🔲 구현 예정 |
| Conversation State Builder | state 구성 및 patch | 🔲 구현 예정 |
| Recent Context Retriever | 최근 N개 + keyword overlap | 🔲 구현 예정 |
| Semantic Compressor (heuristic) | 중복 제거 + 구조화 | 🔲 구현 예정 |
| Prompt Synthesizer | structured prompt 생성 | 🔲 구현 예정 |
| EXAONE provider profile | 한국어 + 7.8b 최적화 | 🔲 구현 예정 |
| 기본 테스트 suite | unit + golden prompt test | 🔲 구현 예정 |
| chat_demo 연동 테스트 | 실제 대화 흐름 검증 | ✅ 완료 |

---

## Phase 2 — Practical Context Engineering

**목표**: 다양한 입력 타입을 실전 환경에서 안정적으로 처리하고,
UCE를 외부 프로젝트(reasondock, NewSpeed)에 내장 가능한 수준으로 완성한다.

**구현 항목**:

| 항목 | 설명 | 상태 |
|------|------|------|
| Content-Type Aware Processing | markdown / code / docx / xlsx / text 타입별 분기 처리 | ✅ 완료 |
| Structure-Preserving Chunking | heading / function / table 단위 semantic boundary 기반 분할 | ✅ 완료 |
| document_loader (docx/xlsx) | python-docx / openpyxl 기반 문서 추출 및 markdown 변환 | ✅ 완료 |
| current_message optional | query 없이 전체 중요도 순 압축 모드 지원 | ✅ 완료 |
| Explainable Retrieval debug | score breakdown / survived / dropped 출력 | ✅ 완료 |
| EXAONE comparison runner | raw prompt vs UCE prompt_pack 응답 비교 | ✅ 완료 |
| Adaptive Compression | intent별 보존 항목 분기 | ✅ 완료 |
| Context Importance Scoring | heading / coherence / intent / constraint 기반 multi-factor scoring | ✅ 완료 |
| xlsx 전체 전달 모드 | SpreadsheetAdapter 없이 전체 시트를 context로 전달 | ✅ 완료 |
| reasondock 내장 | 대화형 채팅 앱 add-on 통합 | 🔲 진행 예정 |
| NewSpeed 내장 | 뉴스 원문 → UCE 압축 → EXAONE 이벤트 추출 파이프라인 통합 | 🔲 진행 예정 |
| Scenario fixtures | continue / topic-shift / long / constraint-sensitive 케이스 | 🔲 진행 예정 |
| Manual evaluation rubric | constraint preservation / hallucination / continuity 기준 | 🔲 진행 예정 |

**조건**: Phase 1 MVP 완료 후 진행. 현재 진행 중.

상세 설계: [Phase 2 Validation Strategy](./phase2-validation.md)

### Phase 2 — xlsx 처리 방침

Phase 2에서 xlsx/csv는 **전체 시트를 context로 전달**하는 방식을 사용한다.

```text
xlsx 파일 입력
    ↓
document_loader → sheet별 markdown 테이블 변환
    ↓
structure_splitter → sheet 단위 섹션 분할
    ↓
전체 내용 → UCE context → LLM 전달
    ↓
LLM이 집계 / 필터 / 카운트 직접 수행
```

**한계**: 행 수가 많을 경우 token limit 초과 가능. LLM의 수치 연산 정확도 보장 불가.
이 한계는 Phase 3의 SpreadsheetAdapter로 해결한다.

---

## Phase 3 — Type-Aware Preprocessing Runtime

**목표**: 입력 타입별 전용 Adapter 아키텍처를 도입하여
UCE를 범용 type-aware preprocessing runtime으로 발전시킨다.

**구현 항목**:

| 항목 | 설명 |
|------|------|
| SpreadsheetAdapter | 자연어 → QueryPlan → pandas 실행 → facts 주입 |
| LogAdapter | timestamp grouping / trace 보존 / error chain 추출 |
| CodeAdapter 고도화 | AST-lite symbol indexing / call relation 보존 |
| Adaptive compression 고도화 | intent + model profile 동적 분기 |
| Narrative state tracking | topic/decision/constraint node 기반 대화 구조화 |
| Relation-aware memory selection | 관계 기반 memory 우선순위 결정 |
| Prompt quality evaluation | 생성된 prompt의 품질 자체 평가 |
| Dynamic context prioritization | 실시간 context 중요도 재계산 |

### Phase 3 — SpreadsheetAdapter 상세 설계

xlsx/csv는 semantic document가 아니라 **임시 데이터베이스**에 가깝다.
사용자 질문의 대부분은 count / filter / aggregation / grouping이며,
raw 행을 LLM에게 통째로 넘기는 것은 비효율적이고 정확도도 낮다.

#### 핵심 원칙

```text
자연어 질문
    ↓
RuleBasedPlanner  — intent 분류 + 컬럼 매핑 (confidence >= 0.7)
    ↓ confidence < 0.7이면
LLM Planner  — QueryPlan JSON만 생성 (코드 실행 안 함)
    ↓
DataFrameExecutor  — deterministic pandas 실행
    ↓
facts[] 주입  — LLM은 설명만 담당
```

LLM은 절대 pandas 코드를 직접 생성하거나 실행하지 않는다.
LLM은 QueryPlan이라는 구조화된 중간 표현만 생성하고,
실제 실행은 DataFrameExecutor가 허용된 연산자 집합으로만 수행한다.

#### Schema Profiling

파일 로딩 시 1회 수행, 결과를 캐시한다.

| 항목 | 내용 |
|------|------|
| 컬럼명 | 원본 그대로 보존 |
| dtype 추론 | str / int / float / datetime |
| null_ratio | 결측치 비율 |
| is_categorical | unique_count < 30 and unique_count/total < 0.1 |
| categorical_values | is_categorical이면 전체 고유값 목록 |
| sample_values | 상위 10개 샘플값 |

#### 컬럼 매핑 전략

"고장대응"이 어느 컬럼의 값인지 추론하는 과정:

```text
1단계: 컬럼명 직접 매칭
2단계: categorical 컬럼의 categorical_values에서 검색  ← 주요 경로
3단계: 부분 문자열 매칭 (confidence 하락)
4단계: LLM fallback — schema_profile + query → column/value 추론만
```

#### QueryPlan Schema

```json
{
  "intent": "COUNT | FILTER | AGGREGATE | GROUP | SORT | TIMESERIES | MIXED",
  "target_sheet": "Sheet1",
  "filters": [
    {"column": "운영업무 세부구분", "operator": "eq", "value": "고장대응"}
  ],
  "group_by": [],
  "aggregate": {"*": "count"},
  "sort_by": [],
  "limit": null,
  "time_column": null,
  "time_granularity": null,
  "confidence": 0.95,
  "planner": "rule_based"
}
```

#### Query Complexity 허용 범위

| 허용 | 비허용 |
|------|--------|
| filter + count / aggregate | JOIN across sheets (complex) |
| GROUP BY + aggregate | 중첩 subquery |
| multi-filter (AND 조건) | 통계 모델링 (regression 등) |
| TIMESERIES 월별/주별 집계 | LLM이 pandas 코드 직접 생성 |
| TOP N + sort | eval() 실행 |

complexity 초과 시 facts에 "처리 범위 초과" 메시지를 넣고 종료한다.

#### Orchestrator 분기

```text
content_type == "xlsx" or "csv"
    → SpreadsheetAdapter 경로
    → structure_splitter / retriever / compressor 생략
    → facts[] 직접 주입

content_type == 그 외
    → 기존 semantic retrieval 경로
```

#### Adapter Interface

```python
class SpreadsheetAdapter:
    def load(self, path: Path) -> None
    def profile(self) -> dict[str, list[ColumnProfile]]
    def plan(self, query: str) -> QueryPlan
    def execute(self, plan: QueryPlan) -> QueryResult
    def to_facts(self, result: QueryResult) -> list[str]
```

---

## 장기 방향

UCE가 지켜야 할 장기 원칙:

```text
Own the assembly.
Do not own the world.
```

UCE는 끝까지 다음이 되지 않는다:
- Memory platform
- Autonomous agent framework
- Full RAG system
- LLM provider

UCE가 될 것:
- 모든 LLM 애플리케이션 앞단에 붙을 수 있는 context preparation layer
- Local LLM과 cloud LLM 모두에서 대화 연속성, token efficiency, prompt quality를 개선하는 범용 middleware

---

## 확장 가능성 (Phase 3 이후)

다음은 UCE의 범위를 벗어나지 않으면서 추가 가능한 방향이다.

### Narrative Graph (읽기 전용)

application이 제공하는 graph memory를 읽어 context assembly에 활용. UCE가 graph를 저장하지는 않는다.

```text
topic node → decision node → constraint node
                ↓
         unresolved question node
```

### Multi-model Orchestration

동일한 Context Pack을 여러 모델에 동시 전달하고 응답을 비교하는 실험적 기능.

### Streaming Context Pack

긴 대화에서 Context Pack을 streaming으로 점진적으로 구성하는 방식.

---

## 하지 않을 것 (영구 제외)

- Vector DB 소유 및 운영
- 사용자 데이터 장기 저장
- Agent workflow 구현
- Tool execution
- 자체 LLM fine-tuning
- 특정 provider 종속 설계

---

## 현재 진행 중인 작업 (Phase 2)

1. reasondock 내장 통합 작업
2. NewSpeed 내장 통합 작업
3. current_message optional 모드 검증
4. Scenario fixtures 작성
5. Manual evaluation rubric 정의

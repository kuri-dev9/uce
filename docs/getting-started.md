# UCE Getting Started
> Version: 0.3  
> Last Updated: 2026-05-20

---

## 1. Overview

UCE는 Python + FastAPI 기반의 stateless Context Engineering Middleware이다.

UCE는 LLM을 직접 호출하지 않는다. application이 현재 메시지, 최근 대화, 외부 메모리, 문서를 UCE에 전달하면 UCE는 LLM에 넣기 좋은 `prompt_pack`을 반환한다. LLM 호출, conversation 저장, memory 저장은 application이 계속 담당한다.

---

## 2. Requirements

- Python 3.11+
- pip
- Docker 또는 로컬 Python 실행 환경
- 선택: Ollama, EXAONE 3.5 7.8B 등 local LLM

현재 `requirements.txt` 주요 의존성:

```text
fastapi
uvicorn[standard]
pydantic
python-docx
openpyxl
```

`python-docx`와 `openpyxl`은 CLI/document loader에서 `.docx`, `.xlsx`를 markdown으로 변환할 때 사용한다.

---

## 3. Install

```bash
git clone https://github.com/kuri-dev9/uce.git
cd uce

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 4. Run

### Docker

```bash
docker build -t uce:local .
docker run --rm -p 8100:8100 uce:local
```

### Local Development

```bash
python -m app.server
```

또는 FastAPI reload가 필요하면:

```bash
uvicorn app.main:app --reload --port 8100
```

확인:

```bash
curl http://localhost:8100/health
curl http://localhost:8100/status
```

---

## 5. Build Context

```bash
curl -sS -X POST http://localhost:8100/build-context \
  -H "Content-Type: application/json" \
  --data-binary @examples/build-context.sample.json
```

응답의 `prompt_pack.content`를 application이 선택한 LLM에 전달한다.

```python
uce_response = requests.post("http://localhost:8100/build-context", json=payload).json()
prompt = uce_response["prompt_pack"]["content"]

# application이 기존 LLM entrypoint로 prompt를 전달한다.
```

---

## 6. Queryless Document Compression

`current_message`는 optional이다. 메시지가 없거나 빈 문자열이면 UCE는 질문 없이 전체 문서를 중요도 순으로 압축한다.

```bash
python3 scripts/try-uce.py \
  --context docs/architecture.md \
  --debug-retrieval \
  --show-prompts
```

이 모드는 "문서를 먼저 정돈하고 압축된 prompt/context를 보고 싶을 때" 사용한다.

---

## 7. Try One Message

문서 없이 단일 질문 비교:

```bash
python3 scripts/try-uce.py \
  --message "UCE 라고 알아?" \
  --show-prompts
```

문서를 UCE에만 전달하고 raw prompt와 UCE prompt를 비교:

```bash
python3 scripts/try-uce.py \
  --context docs/architecture.md \
  --message "UCE의 Phase 2 목표가 뭐야?" \
  --debug-retrieval \
  --show-prompts
```

중요: raw/normal prompt에는 문서를 넣지 않는다. 그래야 "문서 없이 답하는 LLM"과 "UCE가 문서를 선별/압축해 전달한 LLM"을 비교할 수 있다.

---

## 8. docx / xlsx

CLI는 `.docx`, `.xlsx` 파일을 markdown으로 변환해 기존 UCE pipeline에 전달한다.

```bash
python3 scripts/try-uce.py \
  --context path/to/spec.docx \
  --message "이 문서의 핵심 목표가 뭐야?" \
  --debug-retrieval
```

```bash
python3 scripts/try-uce.py \
  --context path/to/data.xlsx \
  --message "각 시트의 핵심 내용을 요약해줘" \
  --debug-retrieval
```

Phase 2의 xlsx 처리는 sheet를 markdown table로 전달하는 방식이다. 정확한 count/filter/aggregation은 Phase 3 SpreadsheetAdapter 범위다.

---

## 9. Compare Raw vs UCE With Ollama

```bash
ollama pull exaone3.5:7.8b
python3 scripts/compare-ollama.py examples/eval/scenario-01-ghost-constraint.json
```

결과는 `--save` 또는 runner 설정에 따라 `runs/` 아래에 저장된다. 기본 개발 검증은 pytest가 아니라 scenario runner와 수동 확인 중심이다.

---

## 10. Integration Pattern

기존 backend에 붙일 때는 UCE를 HTTP add-on으로 둔다.

```text
Frontend
  -> Backend
  -> UCE /build-context
  -> Backend LLM entrypoint
  -> LLM
```

실패 시 반드시 legacy prompt flow로 fallback한다.

```python
try:
    uce_result = await uce_client.build_context(...)
    messages = convert_prompt_pack(uce_result["prompt_pack"])
except Exception:
    messages = legacy_messages
```

UCE는 conversation DB를 소유하지 않는다. 기존 application이 conversation, messages, storage, LLM orchestration을 계속 소유한다.

---

## 11. Next Docs

- [Architecture](./architecture.md)
- [API Reference](./api-reference.md)
- [Roadmap](./roadmap.md)
- [Phase 2 Validation](./phase2-validation.md)


# UCE Getting Started
> Version: 0.1  
> Last Updated: 2026-05-19

---

## 1. 개요

이 문서는 UCE를 처음 설치하고 실행하는 과정을 안내한다.

UCE는 Python + FastAPI 기반의 HTTP API 서버이다. 기존 chat backend에 add-on으로 붙이는 형태로 사용한다.

---

## 2. 사전 요구사항

- Python 3.11+
- pip
- (선택) Ollama — Local LLM 실행 시 필요

---

## 3. 설치

```bash
# 저장소 클론
git clone https://github.com/yourname/uce.git
cd uce

# 가상환경 생성
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

`requirements.txt` 기본 구성:

```text
fastapi>=0.110.0
uvicorn>=0.29.0
pydantic>=2.0.0
tiktoken>=0.6.0
pytest>=8.0.0
httpx>=0.27.0
```

---

## 4. 실행

```bash
uvicorn app.main:app --reload --port 8100
```

서버가 실행되면 다음 주소에서 접근 가능하다:

- API: `http://localhost:8100`
- 자동 문서: `http://localhost:8100/docs`
- Health check: `http://localhost:8100/health`

---

## 5. 기본 사용 흐름

### Step 1: Context Pack 요청

chat backend에서 UCE로 현재 대화를 전달한다.

```bash
curl -X POST http://localhost:8100/build-context \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_session_001",
    "current_message": {
      "role": "user",
      "content": "UCE가 뭔지 설명해줘.",
      "created_at": "2026-05-19T10:00:00+09:00"
    },
    "recent_messages": [],
    "previous_state": null,
    "optional_memories": [],
    "options": {
      "max_prompt_tokens": 4000,
      "target_model": "ollama:exaone3.5:7.8b",
      "compression_level": "medium",
      "include_trace": true
    }
  }'
```

### Step 2: 반환된 prompt_pack으로 LLM 호출

UCE가 반환한 `prompt_pack.content`를 그대로 LLM에 전달한다.

```python
# 예시: Ollama 호출
import httpx

# 1. UCE에서 prompt_pack 받기
uce_response = httpx.post("http://localhost:8100/build-context", json=payload)
prompt_pack = uce_response.json()["prompt_pack"]["content"]
new_state = uce_response.json()["conversation_state"]

# 2. Ollama에 prompt_pack 전달
ollama_response = httpx.post("http://localhost:11434/api/generate", json={
    "model": "exaone3.5:7.8b",
    "prompt": prompt_pack,
    "stream": False
})
llm_answer = ollama_response.json()["response"]
```

### Step 3: 응답 분석 요청

LLM 응답을 UCE로 보내 다음 state를 받는다.

```python
analyze_response = httpx.post("http://localhost:8100/analyze-response", json={
    "session_id": "test_session_001",
    "current_message": {"role": "user", "content": "UCE가 뭔지 설명해줘."},
    "assistant_response": {"role": "assistant", "content": llm_answer},
    "conversation_state": new_state,
    "options": {
        "extract_memory_candidates": True,
        "extract_open_questions": True
    }
})

state_patch = analyze_response.json()["next_state_patch"]
# state_patch를 저장해두고 다음 턴에 previous_state로 사용
```

### Step 4: 다음 턴에 state 전달

```python
# 다음 턴 요청 시 previous_state에 이전 state 전달
payload_next_turn = {
    "session_id": "test_session_001",
    "current_message": {...},
    "recent_messages": [...],
    "previous_state": new_state,  # ← 이전 턴 state
    ...
}
```

---

## 6. Ollama + EXAONE 3.5 7.8b 설정

```bash
# Ollama 설치 (미설치 시)
curl -fsSL https://ollama.com/install.sh | sh

# EXAONE 3.5 7.8b 다운로드
ollama pull exaone3.5:7.8b

# 실행 확인
ollama run exaone3.5:7.8b "안녕하세요"
```

UCE options에서 `target_model`을 `"ollama:exaone3.5:7.8b"`로 설정하면 EXAONE 최적화 prompt profile이 적용된다.

---

## 7. 테스트 실행

```bash
pytest tests/ -v
```

골든 테스트 (동일 입력 → 안정적인 prompt 구조 검증):

```bash
pytest tests/test_golden.py -v
```

---

## 8. 다음 단계

- [API Reference](./api-reference.md) — 전체 API 명세
- [Implementation Guide](./implementation-guide.md) — 컴포넌트별 구현 가이드
- [Roadmap](./roadmap.md) — 앞으로의 방향

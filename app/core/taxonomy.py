SECTION_TYPES = [
    "overview",
    "architecture",
    "deployment",
    "runtime",
    "config",
    "api",
    "flow",
    "feature",
    "troubleshooting",
]

QUERY_TYPES = ["what", "where", "how", "config", "api", "troubleshooting"]

TAXONOMY_TREE = {
    "deployment": {
        "keywords": ["docker", "compose", "container", "배포", "실행", "run", "서비스", "service", "port"],
    },
    "architecture": {
        "keywords": ["구조", "아키텍처", "architecture", "설계", "backend", "frontend", "middleware"],
    },
    "config": {
        "keywords": ["설정", "환경변수", "config", ".env", "options", "settings"],
    },
    "api": {
        "keywords": ["api", "endpoint", "http", "rest", "curl", "호출", "요청", "response"],
    },
    "runtime": {
        "keywords": ["런타임", "runtime", "동작", "실행 중", "프로세스", "process"],
    },
    "overview": {
        "keywords": ["개요", "overview", "소개", "목표", "introduction", "주요", "기능"],
    },
    "flow": {
        "keywords": ["흐름", "flow", "과정", "절차", "단계", "step", "→", "pipeline"],
    },
    "feature": {
        "keywords": ["기능", "feature", "지원", "support", "특징"],
    },
    "troubleshooting": {
        "keywords": ["오류", "에러", "error", "문제", "실패", "해결", "fix"],
    },
}

QUERY_TYPE_RULES = {
    "where": ["어디", "어디서", "where", "위치", "실행", "수행", "동작", "어느"],
    "how": ["어떻게", "방법", "how", "절차", "과정", "단계"],
    "config": ["설정", "환경변수", "config", ".env", "options"],
    "api": ["api", "endpoint", "curl", "호출", "요청", "엔드포인트"],
    "troubleshooting": ["오류", "에러", "error", "문제", "안 됨", "실패", "왜 안"],
    "what": ["뭐야", "무엇", "what", "정의", "설명", "소개", "역할"],
}

QUERY_TAXONOMY_BOOST: dict[str, dict[str, float]] = {
    "where": {"deployment": 0.15, "runtime": 0.10, "architecture": 0.08},
    "how": {"flow": 0.12, "architecture": 0.08, "feature": 0.06},
    "config": {"config": 0.20, "deployment": 0.08},
    "api": {"api": 0.20, "flow": 0.08},
    "troubleshooting": {"troubleshooting": 0.18, "config": 0.08},
}


def classify_query_type(message: str) -> str:
    """Rule-based query type classification. No LLM required."""
    lowered = (message or "").lower()
    scores = {
        query_type: sum(1 for keyword in keywords if keyword.lower() in lowered)
        for query_type, keywords in QUERY_TYPE_RULES.items()
    }
    best_type = max(QUERY_TYPE_RULES, key=lambda query_type: scores[query_type])
    return best_type if scores[best_type] > 0 else "what"


def classify_chunk_taxonomy(content: str, header_path: str) -> list[str]:
    """Classify a chunk taxonomy from its content and header path."""
    combined = f"{header_path or ''}\n{content or ''}".lower()
    matched = [
        taxonomy
        for taxonomy, config in TAXONOMY_TREE.items()
        if any(keyword.lower() in combined for keyword in config["keywords"])
    ]
    return matched or ["overview"]


def apply_taxonomy_boost(score: float, chunk_taxonomy: list[str], query_type: str) -> float:
    """Boost a retrieval score by taxonomy/query-type alignment."""
    boosts = QUERY_TAXONOMY_BOOST.get(query_type, {})
    boost = max((boosts.get(taxonomy, 0.0) for taxonomy in set(chunk_taxonomy)), default=0.0)
    return min(1.0, score + boost)

import time

from fastapi import APIRouter

from app.adapters.provider_profiles import PROFILES
from app.api.schemas import (
    AnalyzeResponseRequest,
    AnalyzeResponseResponse,
    BuildContextRequest,
    BuildContextResponse,
    HealthResponse,
    StatusResponse,
)
from app.core.orchestrator import build_context
from app.core.response_analyzer import analyze_response


START_TIME = time.time()
router = APIRouter()


@router.post("/build-context", response_model=BuildContextResponse)
def route_build_context(req: BuildContextRequest) -> BuildContextResponse:
    return build_context(req)


@router.post("/analyze-response", response_model=AnalyzeResponseResponse)
def route_analyze_response(req: AnalyzeResponseRequest) -> AnalyzeResponseResponse:
    return analyze_response(req)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version="0.1.0",
        components={
            "intent_analyzer": "ok",
            "retriever": "ok",
            "compressor": "ok",
            "prompt_synthesizer": "ok",
        },
    )


@router.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    return StatusResponse(
        compression_level="medium",
        intent_mode="rule_based",
        target_model_note="EXAONE 3.5 7.8b is the first target profile, not a model limit.",
        active_provider_profiles=list(PROFILES.keys()),
        uptime_seconds=int(time.time() - START_TIME),
    )

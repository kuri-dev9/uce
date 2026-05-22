import re
from app.api.schemas import DocumentInput, DenoiseRequest, DenoiseResponse
from app.core import structure_splitter


_NOISE_PATTERNS = [
    re.compile(r"^\S+@\S+\.\S+$"),
    re.compile(r"^https?://\S+$"),
    re.compile(r"^\d+반응"),
    re.compile(r"^\([\w=]+\)\s+\S+\s+기자\s*="),
    re.compile(r"^[+\d]\s*\S+\s+기자$"),
    re.compile(r"^(SNS|공유|인쇄|글자\s*크기|텍스트\s*음성)"),
]


def _is_noise_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return any(p.search(stripped) for p in _NOISE_PATTERNS)


def _clean_section_content(content: str) -> str:
    lines = content.splitlines()
    cleaned = [line for line in lines if not _is_noise_line(line)]
    return "\n".join(cleaned).strip()


def denoise_document(req: DenoiseRequest) -> DenoiseResponse:
    doc_input = DocumentInput(
        id=req.document_id or "denoise_target",
        title=req.title or req.source or "document",
        content=req.content,
        content_type=req.content_type,
        source=req.source or "denoise",
        importance=1.0,
    )

    sections = structure_splitter.split_documents(
        documents=[doc_input],
        enabled=True,
    )

    if not sections:
        cleaned = _clean_section_content(req.content)
        return DenoiseResponse(
            document_id=req.document_id,
            original_chars=len(req.content),
            denoised_chars=len(cleaned),
            reduction_ratio=round(1 - len(cleaned) / max(len(req.content), 1), 4),
            denoised_content=cleaned,
            sections_found=0,
        )

    cleaned_parts = []
    for section in sections:
        cleaned = _clean_section_content(section.content)
        if cleaned:
            cleaned_parts.append(cleaned)

    denoised = "\n\n".join(cleaned_parts)

    return DenoiseResponse(
        document_id=req.document_id,
        original_chars=len(req.content),
        denoised_chars=len(denoised),
        reduction_ratio=round(1 - len(denoised) / max(len(req.content), 1), 4),
        denoised_content=denoised,
        sections_found=len(sections),
    )

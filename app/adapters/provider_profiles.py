from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    max_prompt_tokens: int
    compression_level: str
    prompt_language: str
    note: str


PROFILES: dict[str, ProviderProfile] = {
    "generic": ProviderProfile(
        name="generic",
        max_prompt_tokens=4000,
        compression_level="medium",
        prompt_language="mixed_ko_en",
        note="Provider-neutral default profile.",
    ),
    "ollama_exaone_7b": ProviderProfile(
        name="ollama_exaone_7b",
        max_prompt_tokens=4000,
        compression_level="medium",
        prompt_language="mixed_ko_en",
        note="First target profile for Korean conversations. UCE is not limited to this model.",
    ),
    "ollama_qwen": ProviderProfile(
        name="ollama_qwen",
        max_prompt_tokens=4000,
        compression_level="medium",
        prompt_language="mixed_ko_en",
        note="Generic Qwen local profile.",
    ),
    "ollama_gemma": ProviderProfile(
        name="ollama_gemma",
        max_prompt_tokens=4000,
        compression_level="medium",
        prompt_language="mixed_ko_en",
        note="Generic Gemma local profile.",
    ),
    "cloud_large": ProviderProfile(
        name="cloud_large",
        max_prompt_tokens=8000,
        compression_level="light",
        prompt_language="mixed_ko_en",
        note="Large cloud model profile.",
    ),
}


def resolve_profile(target_model: str) -> ProviderProfile:
    lowered = target_model.lower()
    if "exaone" in lowered:
        return PROFILES["ollama_exaone_7b"]
    if "qwen" in lowered:
        return PROFILES["ollama_qwen"]
    if "gemma" in lowered:
        return PROFILES["ollama_gemma"]
    if lowered.startswith("openai:") or lowered.startswith("anthropic:") or "claude" in lowered:
        return PROFILES["cloud_large"]
    return PROFILES["generic"]

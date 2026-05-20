def estimate_tokens(text: str) -> int:
    """Small dependency-free token estimate tuned for Korean/English mixed prompts."""
    if not text:
        return 0

    korean_chars = sum(1 for ch in text if "\uac00" <= ch <= "\ud7a3")
    non_space_chars = sum(1 for ch in text if not ch.isspace())
    ascii_words = len([part for part in text.split() if part.isascii()])

    korean_estimate = korean_chars // 2
    remainder_estimate = max(0, non_space_chars - korean_chars) // 4
    return max(1, korean_estimate + remainder_estimate + ascii_words // 2)

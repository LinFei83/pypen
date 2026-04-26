from wonderwords import RandomWord

from app.utils.logging_config import logger

_word_generator = RandomWord()

_ASCII_ONLY = r"^[a-zA-Z]+$"


def _ascii_word(part_of_speech: str) -> str:
    return _word_generator.word(
        include_parts_of_speech=[part_of_speech],
        regex=_ASCII_ONLY,
    )


def generate_prefix() -> str:
    adjective = _ascii_word("adjectives")
    noun = _ascii_word("nouns")
    prefix = f"{adjective} {noun}"
    logger.info(f"Generated prefix: {prefix}")
    return prefix

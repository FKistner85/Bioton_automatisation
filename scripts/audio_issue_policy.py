"""Separate expected-duration notes from technical audio failures."""
import re

_DURATION_NOTE = re.compile(r"^(?:sound_)?duration_not_[0-9]+(?:\.[0-9]+)?s(?::.*)?$")


def issue_tokens(values):
    if isinstance(values, (list, tuple)):
        return [str(v).strip() for v in values if str(v).strip()]
    return [v.strip() for v in str(values).split("|")
            if v.strip() and v.strip().lower() not in {"nan", "none", "<na>"}]


def duration_notes_only(values) -> bool:
    tokens = issue_tokens(values)
    return bool(tokens) and all(_DURATION_NOTE.fullmatch(v) for v in tokens)


def has_blocking_audio_issues(values) -> bool:
    return any(not _DURATION_NOTE.fullmatch(v) for v in issue_tokens(values))

"""Detect when the athlete explicitly affirms prior assistant content for memory write."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConfirmationSignal:
    confirmed: bool
    reason: str


# Short affirmations that typically refer to the previous assistant turn.
_AFFIRMATION_PHRASES: tuple[tuple[str, str], ...] = (
    # RU — save / remember assistant output
    (r"(?:да,?\s*)?(?:сохрани|запомни)\s+(?:это|этот\s+вывод|вывод|анализ)", "ru_save_assistant"),
    (r"запомни\s+этот\s+вывод", "ru_remember_conclusion"),
    (r"(?:да,?\s*)?верно\b", "ru_verno"),
    (r"это\s+правда\b", "ru_eto_pravda"),
    (r"согласна?\s+с\s+анализ", "ru_agree_analysis"),
    (r"подтверждаю\s+(?:анализ|вывод|это)", "ru_confirm_analysis"),
    # EN
    (r"(?:yes,?\s*)?(?:save|store)\s+(?:this|that|it)\b", "en_save"),
    (r"remember\s+(?:this|that)\s+(?:conclusion|analysis|finding)", "en_remember"),
    (r"\bthat(?:'s| is)\s+(?:correct|true|right)\b", "en_that_is_true"),
    (r"\bcorrect\b", "en_correct"),
    (r"\bagree\s+with\s+(?:the\s+)?analysis\b", "en_agree_analysis"),
    # Schedule / HITL (user confirms a proposal — still user-sourced, not assistant facts)
    (r"подтверждаю\s+план", "ru_confirm_plan"),
    (r"confirm(?:ing)?\s+(?:the\s+)?(?:plan|schedule|block)\b", "en_confirm_plan"),
)

# Whole-message short replies (after trimming punctuation).
_SHORT_CONFIRM_REPLIES: frozenset[str] = frozenset(
    {
        "да",
        "верно",
        "правда",
        "согласна",
        "согласен",
        "yes",
        "correct",
        "true",
        "right",
        "ok",
        "okay",
    }
)


def _normalize_reply(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"[!?.…]+$", "", t).strip()
    return t


def detect_explicit_user_confirmation(user_text: str) -> ConfirmationSignal:
    """
    True when the athlete explicitly asks to persist or endorses prior assistant output.

    Used to gate assistant-derived memory extraction — not for general sport facts
    the athlete states in their own words (those use user-only extraction).
    """
    blob = (user_text or "").strip()
    if not blob:
        return ConfirmationSignal(False, "empty")

    lower = blob.lower()
    for pattern, reason in _AFFIRMATION_PHRASES:
        if re.search(pattern, lower, re.IGNORECASE):
            return ConfirmationSignal(True, reason)

    # Single short line often means "yes, keep what you said"
    lines = [ln.strip() for ln in blob.splitlines() if ln.strip()]
    if len(lines) == 1:
        norm = _normalize_reply(lines[0])
        if norm in _SHORT_CONFIRM_REPLIES and len(norm) <= 24:
            return ConfirmationSignal(True, "short_affirmation_reply")

    return ConfirmationSignal(False, "no_explicit_confirmation")

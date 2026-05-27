"""
Athlete emotional tone + consent-to-analyze (HITL-style) for prompt routing.

Future: onboarding survey writes interaction.support.* preferences to LTM.
"""

from __future__ import annotations

import re
from typing import Any, Literal

InteractionMode = Literal[
    "full_analysis",
    "support_first",
    "celebrate_first",
    "neutral",
]

CoachingTone = Literal["gentle", "direct", "tough"]

_DISTRESS = (
    "проиграл",
    "проиграла",
    "проигры",
    "плохо",
    "груст",
    "расстро",
    "устал",
    "устала",
    "выгор",
    "не получается",
    "не получилось",
    "ошибк",
    "провал",
    "разочар",
    "злой",
    "злая",
    "бесит",
    "депресс",
    "плохое настроение",
    "после поражения",
    "lost",
    "defeat",
    "frustrat",
    "upset",
    "bad mood",
)

_POSITIVE = (
    "выиграл",
    "выиграла",
    "побед",
    "хорошо",
    "отлично",
    "классно",
    "лучший",
    "удалось",
    "получилось",
    "горжусь",
    "рада",
    "рад ",
    "won",
    "great match",
    "best ",
)

_CONSENT = (
    "да",
    "давай",
    "разбер",
    "разобр",
    "хочу",
    "соглас",
    "ок",
    "okay",
    "yes",
    "go ahead",
    "поехали",
    "можно",
    "готова",
    "готов",
)

_REFUSAL = (
    "нет",
    "не хочу",
    "потом",
    "не сейчас",
    "no ",
    "not now",
    "later",
)

# Athlete explicitly wants a debrief now (not just venting about errors)
_EXPLICIT_DEBRIEF = (
    "разбер",
    "разобр",
    "разбери",
    "укажи на ошиб",
    "укажи ошиб",
    "чётк",
    "четк",
    "чёткое понимание",
    "четкое понимание",
    "прямо скаж",
    "прямо укаж",
    "прямо скажи",
    "жёстк",
    "жестк",
    "твёрд",
    "тверд",
    "конкретн",
    "по пунктам",
    "технический разбор",
    "без воды",
    "не потака",
    "debrief",
    "break down",
)

_DEBRIEF_TOPIC = (
    "ошиб",
    "матч",
    "игр",
    "сет ",
    "партия",
    "трениров",
    "performance",
    "match",
)


def detect_emotional_tone(text: str) -> Literal["distressed", "positive", "neutral"]:
    t = text.lower()
    d = sum(1 for w in _DISTRESS if w in t)
    p = sum(1 for w in _POSITIVE if w in t)
    if d > p and d >= 1:
        return "distressed"
    if p > d and p >= 1:
        return "positive"
    return "neutral"


def is_analysis_consent(text: str) -> bool:
    t = text.lower().strip()
    if len(t) > 120:
        return False
    return any(w in t for w in _CONSENT)


def wants_explicit_debrief(text: str) -> bool:
    """User asks for clear error breakdown now — skip support-only turn."""
    t = text.lower()
    if not any(w in t for w in _EXPLICIT_DEBRIEF):
        return False
    return any(w in t for w in _DEBRIEF_TOPIC) or "разбер" in t or "разобр" in t


def normalize_coaching_style(raw: str) -> CoachingTone:
    r = raw.lower()
    if any(x in r for x in ("tough", "жёстк", "жестк", "hard", "твёрд", "твердо")):
        return "tough"
    if any(
        x in r
        for x in ("direct", "прям", "чётк", "четк", "конкрет", "motivational", "мотив")
    ):
        return "direct"
    return "gentle"


def detect_message_coaching_tone(text: str) -> CoachingTone | None:
    t = text.lower()
    if any(w in t for w in ("жёстк", "жестк", "твёрд", "твердо", "tough", "hard")):
        return "tough"
    if any(w in t for w in ("чётк", "четк", "прям", "конкрет", "direct", "без воды")):
        return "direct"
    return None


def resolve_coaching_tone(
    user_input: str,
    memory_context: str,
    mode: InteractionMode,
) -> CoachingTone:
    """How blunt the analyst should be this turn."""
    if mode not in ("full_analysis", "neutral"):
        return "gentle"
    msg_tone = detect_message_coaching_tone(user_input)
    prefs = parse_support_preferences(memory_context)
    pref_tone = normalize_coaching_style(prefs.get("style", "gentle"))
    if msg_tone:
        return msg_tone
    if mode == "full_analysis":
        return pref_tone
    if pref_tone in ("direct", "tough"):
        return pref_tone
    return "gentle"


def is_analysis_refusal(text: str) -> bool:
    t = text.lower().strip()
    if len(t) > 80:
        return False
    return any(w in t for w in _REFUSAL)


def memory_has_pending_offer(memory_context: str) -> bool:
    if not memory_context:
        return False
    return bool(
        re.search(
            r"interaction\.pending_offer|pending_offer|ожидает согласия на разбор",
            memory_context,
            re.I,
        )
    )


def parse_support_preferences(memory_context: str) -> dict[str, str]:
    """Read interaction.support.* lines from assembled memory context."""
    prefs: dict[str, str] = {}
    if not memory_context:
        return prefs
    for line in memory_context.splitlines():
        m = re.search(
            r"interaction\.support\.(\w+)\s*[:=]\s*(.+)",
            line,
            re.I,
        )
        if m:
            prefs[m.group(1).lower()] = m.group(2).strip()
    return prefs


def resolve_interaction_mode(
    user_input: str,
    *,
    memory_context: str = "",
    prior_offer: str | None = None,
    planner_mode: str | None = None,
) -> InteractionMode:
    """
    Decide how Analyst/Health should respond this turn.

    prior_offer: from graph checkpoint (analysis_debrief | performance_deeper)
    """
    tone = detect_emotional_tone(user_input)
    pending = prior_offer or (
        "analysis_debrief" if memory_has_pending_offer(memory_context) else None
    )

    if wants_explicit_debrief(user_input):
        return "full_analysis"

    if planner_mode in ("full_analysis", "support_first", "celebrate_first", "neutral"):
        if planner_mode != "neutral":
            # Consent overrides celebrate/support when user agreed to debrief
            if pending and is_analysis_consent(user_input):
                return "full_analysis"
            if planner_mode == "support_first" and not (
                pending and is_analysis_consent(user_input)
            ):
                return "support_first"
            if planner_mode == "celebrate_first" and not (
                pending and is_analysis_consent(user_input)
            ):
                return "celebrate_first"
            return planner_mode  # type: ignore[return-value]

    if pending and is_analysis_consent(user_input):
        return "full_analysis"
    if pending and is_analysis_refusal(user_input):
        return "support_first" if tone == "distressed" else "neutral"

    if tone == "distressed":
        return "support_first"
    if tone == "positive":
        return "celebrate_first"
    return "neutral"


def support_instructions_block(
    memory_context: str,
    mode: InteractionMode,
) -> str:
    prefs = parse_support_preferences(memory_context)
    style = prefs.get("style", "gentle — empathy first, no blame")
    when_low = prefs.get(
        "when_low",
        "validate feelings; do not list mistakes unless athlete explicitly asked",
    )
    when_high = prefs.get(
        "when_high",
        "celebrate briefly; offer optional deeper review only if they want",
    )

    lines = [
        "## Athlete support preferences (respect these)",
        f"- Style: {style}",
        f"- When mood is low: {when_low}",
        f"- When mood is high: {when_high}",
    ]
    if mode == "support_first":
        lines.append(
            "- THIS TURN: support_only — no error breakdown, no JSON, no harsh coaching tone."
        )
        lines.append(
            "- End with ONE gentle question offering analysis, e.g. "
            "'Хочешь, вместе разберём ошибки по пунктам? (да/нет)'"
        )
    elif mode == "celebrate_first":
        lines.append(
            "- THIS TURN: celebrate success first — no immediate critique."
        )
        lines.append(
            "- End offering optional next step (deeper review or plan), wait for yes."
        )
    elif mode == "full_analysis":
        tone = normalize_coaching_style(style)
        if tone == "tough":
            lines.append(
                "- THIS TURN: full debrief — be direct and firm. Name each error clearly "
                "(numbered list). Cause → consequence → one fix. No vague comfort, no sugarcoating."
            )
            lines.append(
                "- Still forbidden: insults, shame, «ты лох», comparisons that humiliate."
            )
        elif tone == "direct":
            lines.append(
                "- THIS TURN: full debrief — clear, structured, no fluff. "
                "Point out mistakes explicitly; athlete asked for clarity, not coddling."
            )
            lines.append(
                "- Still forbidden: insults and humiliation — be tough on errors, respectful to the person."
            )
        else:
            lines.append(
                "- Athlete agreed to debrief — analyze errors constructively and clearly, still no insults."
            )
    return "\n".join(lines)


def offer_followup_for_mode(mode: InteractionMode) -> str | None:
    if mode == "support_first":
        return "analysis_debrief"
    if mode == "celebrate_first":
        return "performance_deeper"
    return None

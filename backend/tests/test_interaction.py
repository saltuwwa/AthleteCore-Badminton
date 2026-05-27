from app.graph.interaction import (
    detect_emotional_tone,
    is_analysis_consent,
    resolve_coaching_tone,
    resolve_interaction_mode,
    wants_explicit_debrief,
)


def test_distress_support_first():
    assert detect_emotional_tone("Проиграла, расстроена, куча ошибок") == "distressed"
    mode = resolve_interaction_mode("Проиграла, устала, всё плохо")
    assert mode == "support_first"


def test_positive_celebrate():
    assert detect_emotional_tone("Выиграла финал, отлично сыграла") == "positive"
    assert resolve_interaction_mode("Выиграла!") == "celebrate_first"


def test_consent_after_offer():
    mode = resolve_interaction_mode(
        "да",
        prior_offer="analysis_debrief",
        planner_mode="neutral",
    )
    assert mode == "full_analysis"


def test_consent_short():
    assert is_analysis_consent("давай разберём")


def test_explicit_debrief_overrides_distress():
    msg = "Проиграла, но разбери мои ошибки чётко по пунктам"
    assert wants_explicit_debrief(msg)
    assert resolve_interaction_mode(msg) == "full_analysis"


def test_direct_tone_from_message():
    ctx = "interaction.support.style: gentle"
    tone = resolve_coaching_tone(
        "Жёстко укажи все ошибки в матче",
        ctx,
        "full_analysis",
    )
    assert tone == "tough"


def test_direct_tone_from_memory():
    ctx = "interaction.support.style: direct"
    tone = resolve_coaching_tone("да", ctx, "full_analysis")
    assert tone == "direct"

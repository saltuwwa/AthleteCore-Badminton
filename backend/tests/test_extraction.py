import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.memory.confirmation import detect_explicit_user_confirmation
from app.memory.constants import SOURCE_CONFIRMED_ANALYSIS, SOURCE_USER
from app.memory.extraction import (
    assistant_messages_only,
    build_user_extraction_request,
    concat_user_text,
    extract_memories_from_turn,
    extract_memories_from_user_turn,
    latest_assistant_text,
    merge_extraction_candidates,
    user_messages_only,
)
from app.memory.write_gate import MemoryWriteGate


TURN = [
    {"role": "user", "content": "Вчера была тренировка 90 минут"},
    {
        "role": "assistant",
        "content": "Главная ошибка — поздний contact point и слабый split-step.",
    },
]

TURN_CONFIRM = [
    {"role": "user", "content": "Сравни с прошлым матчем"},
    {
        "role": "assistant",
        "content": "Паттерн: поздний удар на бэкхенде, риск HIGH.",
    },
    {"role": "user", "content": "Да, сохрани этот вывод"},
]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Да, сохрани этот вывод", True),
        ("верно", True),
        ("запомни этот вывод", True),
        ("это правда", True),
        ("Remember this analysis", True),
        ("yes, save this", True),
        ("Вчера была тренировка", False),
        ("Сравни с матчем 15 апреля", False),
    ],
)
def test_detect_explicit_user_confirmation(text: str, expected: bool):
    signal = detect_explicit_user_confirmation(text)
    assert signal.confirmed is expected


def test_user_messages_only_excludes_assistant():
    assert len(user_messages_only(TURN)) == 1
    assert len(assistant_messages_only(TURN)) == 1
    assert "contact point" in latest_assistant_text(TURN)


def test_build_user_extraction_request_has_no_assistant():
    user_msgs = user_messages_only(TURN)
    req = build_user_extraction_request(user_msgs, reference_date=date(2026, 5, 29))
    assert "USER messages" in req["user"]
    assert "contact point" not in req["user"]
    assert "assistant" not in req["user"].lower()


@pytest.mark.asyncio
async def test_extract_user_turn_stamps_source_user():
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(
                    {
                        "memories": [
                            {
                                "type": "event",
                                "key": "training.session.latest",
                                "value": "Силовая 90 мин",
                                "event_type": "training_log",
                            }
                        ]
                    }
                )
            )
        )
    ]
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=mock_resp)

    out = await extract_memories_from_user_turn(
        client,
        MagicMock(extraction_model="gpt-4o-mini"),
        TURN,
        reference_date=date(2026, 5, 29),
    )
    assert len(out) == 1
    assert out[0]["source"] == SOURCE_USER
    call_args = client.chat.completions.create.await_args.kwargs["messages"]
    user_blob = call_args[1]["content"]
    assert "contact point" not in user_blob


@pytest.mark.asyncio
async def test_extract_turn_skips_assistant_without_confirmation():
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(message=MagicMock(content=json.dumps({"memories": []})))
    ]
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=mock_resp)

    await extract_memories_from_turn(
        client,
        MagicMock(extraction_model="gpt-4o-mini"),
        TURN,
        reference_date=date(2026, 5, 29),
    )
    assert client.chat.completions.create.await_count == 1


@pytest.mark.asyncio
async def test_extract_turn_confirmed_assistant_second_call():
    user_resp = MagicMock()
    user_resp.choices = [
        MagicMock(message=MagicMock(content=json.dumps({"memories": []})))
    ]
    confirmed_resp = MagicMock()
    confirmed_resp.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(
                    {
                        "memories": [
                            {
                                "type": "fact",
                                "key": "performance.error.pattern",
                                "value": "Поздний удар на бэкхенде",
                            }
                        ]
                    }
                )
            )
        )
    ]
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(side_effect=[user_resp, confirmed_resp])

    out = await extract_memories_from_turn(
        client,
        MagicMock(extraction_model="gpt-4o-mini"),
        TURN_CONFIRM,
        reference_date=date(2026, 5, 29),
    )
    assert client.chat.completions.create.await_count == 2
    assert len(out) == 1
    assert out[0]["source"] == SOURCE_CONFIRMED_ANALYSIS
    assert out[0]["is_user_confirmed"] is True


def test_merge_user_wins_on_key_collision():
    user = [{"key": "match.latest", "value": "from user", "source": SOURCE_USER}]
    confirmed = [{"key": "match.latest", "value": "from assistant", "source": SOURCE_CONFIRMED_ANALYSIS}]
    merged = merge_extraction_candidates(user, confirmed)
    assert merged[0]["value"] == "from user"


def test_write_gate_blocks_assistant_and_unconfirmed_analysis():
    gate = MemoryWriteGate()
    assistant = {
        "type": "fact",
        "key": "performance.error.pattern",
        "value": "fake",
        "source": "assistant",
    }
    unconfirmed = {
        **assistant,
        "source": SOURCE_CONFIRMED_ANALYSIS,
        "is_user_confirmed": False,
    }
    assert gate.filter_candidates([assistant]) == []
    assert gate.filter_candidates([unconfirmed]) == []


def test_concat_user_text_multiline_turn():
    blob = concat_user_text(TURN_CONFIRM)
    assert "сохрани" in blob
    assert blob.count("\n\n") == 1  # two user messages

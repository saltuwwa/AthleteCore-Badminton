import pytest

from app.mcp_tools.methodology import search_sports_methodology


def test_search_methodology_footwork():
    hits = search_sports_methodology("footwork split step lunge", top_k=3)
    # May be empty in CI without output/ — skip assert if no books
    if not hits:
        pytest.skip("no output/*.md in workspace")
    assert hits[0]["source"].endswith(".md")
    assert hits[0]["snippet"]
    assert hits[0]["score"] > 0


@pytest.mark.asyncio
async def test_schedule_seed_and_list():
    from app.database import AsyncSessionLocal, init_db
    from app.mcp_tools.schedule import get_training_schedule

    await init_db()
    async with AsyncSessionLocal() as session:
        payload = await get_training_schedule(user_id="test_mcp_user")
        await session.commit()
    assert payload["count"] >= 1
    assert payload["events"][0]["title"]

#!/usr/bin/env python3
"""
AthleteCore MCP server (stdio).

Tools:
  - recall_athlete_memory — LTM hybrid recall for the athlete
  - search_sports_methodology — RAG over output/*.md (LlamaParse books)
  - get_training_schedule — calendar blocks (SQLite)
  - propose_training_block — HITL draft event (pending_confirmation)

Run from project root:
  set PYTHONPATH=backend
  python -m mcp_server.server

Cursor: see .cursor/mcp.json
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# backend/app on path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(_ROOT / "backend" / ".env", override=False)
load_dotenv(_ROOT / ".env", override=False)

from mcp.server.fastmcp import FastMCP

from app.database import init_db
from app.mcp_tools.memory import recall_athlete_memory
from app.mcp_tools.methodology import search_sports_methodology
from app.mcp_tools.schedule import get_training_schedule, propose_training_block

mcp = FastMCP(
    "athletecore",
    instructions=(
        "AthleteCore tools for a professional badminton athlete. "
        "Use recall_athlete_memory for personal history and patterns. "
        "Use search_sports_methodology for footwork/technique from coaching PDFs. "
        "Use get_training_schedule before proposing changes; "
        "propose_training_block creates pending events requiring athlete confirmation."
    ),
)


def _run(coro):
    return asyncio.run(coro)


@mcp.tool()
def recall_athlete_memory_tool(
    query: str,
    user_id: str = "aigerim",
    session_id: str = "main",
    max_tokens: int = 900,
) -> str:
    """
    Retrieve relevant long-term memories for the athlete (goals, errors, preferences, past matches).

    Use when analyzing performance, recovery, or personalized advice — not for weather or generic facts.
    """
    result = _run(
        recall_athlete_memory(
            query,
            user_id=user_id,
            session_id=session_id,
            max_tokens=max_tokens,
        )
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def search_sports_methodology_tool(
    query: str,
    top_k: int = 5,
) -> str:
    """
    Search parsed badminton coaching books (Markdown in output/) for technique and drills.

    Use for footwork, stroke technique, training methodology — cite source filename in answers.
    """
    hits = search_sports_methodology(query, top_k=min(top_k, 10))
    return json.dumps({"query": query, "hits": hits}, ensure_ascii=False, indent=2)


@mcp.tool()
def get_training_schedule_tool(
    user_id: str = "aigerim",
    date_from: str = "",
    date_to: str = "",
    include_pending: bool = True,
) -> str:
    """
    List training/match/recovery blocks in a date range (YYYY-MM-DD).

    Empty dates default to today through +14 days. Check conflicts before proposing new blocks.
    """
    kwargs: dict = {"user_id": user_id, "include_pending": include_pending}
    if date_from.strip():
        kwargs["date_from"] = date_from.strip()
    if date_to.strip():
        kwargs["date_to"] = date_to.strip()
    payload = _run(get_training_schedule(**kwargs))
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def propose_training_block_tool(
    title: str,
    event_date: str,
    start_time: str,
    end_time: str,
    user_id: str = "aigerim",
    event_type: str = "TRAINING",
    intensity: int = 3,
    reason: str = "",
) -> str:
    """
    Propose a new calendar block (status pending_confirmation). Athlete must confirm in the app.

    Use after get_training_schedule to avoid overlaps. intensity 1–5 for training load.
    """
    payload = _run(
        propose_training_block(
            user_id=user_id,
            title=title,
            event_date=event_date,
            start_time=start_time,
            end_time=end_time,
            event_type=event_type,
            intensity=intensity,
            reason=reason or None,
        )
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> None:
    _run(init_db())
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

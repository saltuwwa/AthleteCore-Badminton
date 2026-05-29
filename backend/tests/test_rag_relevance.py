"""Tests for methodology RAG relevance filtering."""

from app.mcp_tools.methodology import (
    get_methodology_retrieval_debug,
    search_sports_methodology,
)
from app.rag.relevance_filter import assess_query_domain, filter_methodology_hits


def test_off_topic_historical_query_rejected():
    q = "Who won the 1842 Paris archery gold medal at the ancient Olympics?"
    assess = assess_query_domain(q)
    assert assess["domain_match"] is False
    hits = search_sports_methodology(q, top_k=3)
    assert hits == []
    debug = get_methodology_retrieval_debug()
    assert debug is not None
    assert debug.get("rejection_reason") == "off_domain_query"
    assert debug.get("domain_match") is False


def test_sports_query_domain_match():
    q = "split step footwork lunge badminton"
    assess = assess_query_domain(q)
    assert assess["domain_match"] is True


def test_nonsense_query_low_domain():
    q = "zzqxq footwidget quantum tennis recipe 99999"
    assess = assess_query_domain(q)
    assert assess["domain_match"] is False


def test_filter_rejects_weak_lexical_candidates():
    q = "Who won the 1842 Paris archery gold medal at the ancient Olympics?"
    candidates = [
        {
            "source": "book.md",
            "score": 0.5,
            "snippet": "some generic english coaching filler text",
            "snippet_full": "some generic english coaching filler text about winning",
            "retrieval": "lexical",
        }
    ]
    accepted, debug = filter_methodology_hits(q, candidates, top_k=3)
    assert accepted == []
    assert debug["rejection_reason"] == "off_domain_query"

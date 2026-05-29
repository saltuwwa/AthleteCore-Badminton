"""
Relevance filtering for sports methodology RAG (lexical + vector hits).

Prevents false grounding when queries are off-domain or overlap is too weak.
"""

from __future__ import annotations

import re
from typing import Any

# Sports / badminton / training methodology vocabulary
SPORTS_DOMAIN_KEYWORDS: frozenset[str] = frozenset(
    {
        "badminton",
        "footwork",
        "training",
        "recovery",
        "athlete",
        "coach",
        "match",
        "tournament",
        "serve",
        "serving",
        "clear",
        "drop",
        "smash",
        "lunge",
        "split",
        "step",
        "drill",
        "warmup",
        "injury",
        "fatigue",
        "schedule",
        "court",
        "rally",
        "shuttle",
        "net",
        "stroke",
        "technique",
        "tactical",
        "methodology",
        "подач",
        "бадминтон",
        "работа",
        "ног",
        "трениров",
        "разминк",
        "подача",
        "удар",
        "тактик",
    }
)

# Trivia / general knowledge — not in coaching books scope
OFF_TOPIC_KEYWORDS: frozenset[str] = frozenset(
    {
        "archery",
        "olympics",
        "olympic",
        "ancient",
        "medal",
        "gold medal",
        "silver medal",
        "paris",
        "recipe",
        "quantum",
        "footwidget",
        "zzqxq",
        "president",
        "election",
        "cryptocurrency",
        "bitcoin",
        "weather forecast",
    }
)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "who",
        "won",
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "what",
        "when",
        "where",
        "how",
        "are",
        "was",
        "were",
        "have",
        "has",
        "had",
        "at",
        "in",
        "on",
        "to",
        "of",
        "a",
        "an",
        "is",
        "it",
        "be",
        "by",
        "or",
        "as",
        "their",
        "his",
        "her",
        "its",
    }
)

_HISTORICAL_TRIVIA_RE = re.compile(
    r"\b(who\s+won|when\s+did|which\s+country)\b.{0,80}\b(18|19)\d{2}\b",
    re.I | re.DOTALL,
)

_MIN_LEXICAL_OVERLAP = 0.18
_MIN_LEXICAL_SCORE = 0.14
_MIN_QDRANT_SCORE = 0.35
_MIN_SPORTS_QUERY_SIGNALS = 1


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{3,}", (text or "").lower())
    return set(words)


def _sports_signal_count(query: str, tokens: set[str]) -> int:
    q_lower = query.lower()
    count = len(tokens & SPORTS_DOMAIN_KEYWORDS)
    for phrase in ("split step", "работа ног", "split-step"):
        if phrase in q_lower:
            count += 1
    return count


def _off_topic_signal_count(query: str, tokens: set[str]) -> int:
    q_lower = query.lower()
    count = len(tokens & OFF_TOPIC_KEYWORDS)
    for phrase in ("gold medal", "ancient olympics", "who won"):
        if phrase in q_lower:
            count += 1
    if _HISTORICAL_TRIVIA_RE.search(query):
        count += 2
    if re.search(r"\b(18|19)\d{2}\b", query) and "badminton" not in q_lower:
        if any(w in q_lower for w in ("archery", "olympics", "olympic", "ancient")):
            count += 2
    return count


def assess_query_domain(query: str) -> dict[str, Any]:
    """Whether the query is in AthleteCore methodology domain."""
    query = (query or "").strip()
    tokens = _tokenize(query)
    sig_tokens = tokens - _STOPWORDS
    sports = _sports_signal_count(query, tokens)
    off_topic = _off_topic_signal_count(query, tokens)

    domain_match = sports >= _MIN_SPORTS_QUERY_SIGNALS and sports > off_topic
    if sports == 0 and off_topic >= 1:
        domain_match = False
    if off_topic >= 2 and sports == 0:
        domain_match = False

    return {
        "query": query,
        "domain_match": domain_match,
        "sports_signal_count": sports,
        "off_topic_signal_count": off_topic,
        "significant_token_count": len(sig_tokens),
    }


def _chunk_domain_match(chunk_text: str) -> bool:
    t = chunk_text.lower()
    return any(kw in t for kw in SPORTS_DOMAIN_KEYWORDS if len(kw) >= 4) or any(
        kw in t for kw in ("footwork", "serve", "lunge", "clear", "drop", "подач", "бадминтон")
    )


def _lexical_overlap(query: str, chunk_text: str) -> float:
    q_tokens = _tokenize(query) - _STOPWORDS
    t_tokens = _tokenize(chunk_text)
    if not q_tokens:
        return 0.0
    sports_q = {t for t in q_tokens if t in SPORTS_DOMAIN_KEYWORDS}
    if sports_q:
        overlap = len(sports_q & t_tokens) / max(len(sports_q), 1)
        if overlap > 0:
            return overlap
    return len(q_tokens & t_tokens) / max(len(q_tokens), 1)


def filter_methodology_hits(
    query: str,
    candidates: list[dict],
    *,
    top_k: int = 5,
) -> tuple[list[dict], dict[str, Any]]:
    """
    Accept only domain-relevant chunks. Returns (accepted_hits, debug_dict).
    """
    query = (query or "").strip()
    q_assess = assess_query_domain(query)

    debug: dict[str, Any] = {
        "query": query,
        "domain_match": q_assess["domain_match"],
        "sports_signal_count": q_assess["sports_signal_count"],
        "off_topic_signal_count": q_assess["off_topic_signal_count"],
        "accepted_hits_count": 0,
        "rejected_hits_count": 0,
        "rejection_reason": None,
        "top_score": None,
        "lexical_overlap": None,
        "rejections": [],
    }

    if not query:
        debug["rejection_reason"] = "empty_query"
        return [], debug

    if not q_assess["domain_match"]:
        debug["rejection_reason"] = "off_domain_query"
        debug["rejected_hits_count"] = len(candidates)
        for c in candidates[:5]:
            debug["rejections"].append(
                {
                    "source": c.get("source"),
                    "score": c.get("score"),
                    "reason": "query_off_domain",
                }
            )
        return [], debug

    if not candidates:
        debug["rejection_reason"] = "no_candidates"
        return [], debug

    accepted: list[dict] = []
    for c in candidates:
        snippet = c.get("snippet_full") or c.get("snippet") or ""
        score = float(c.get("score") or 0)
        overlap = _lexical_overlap(query, snippet)
        retrieval = c.get("retrieval", "lexical")
        chunk_domain = _chunk_domain_match(snippet)

        reasons: list[str] = []
        if retrieval == "lexical":
            if score < _MIN_LEXICAL_SCORE:
                reasons.append("weak_lexical_score")
            if overlap < _MIN_LEXICAL_OVERLAP:
                reasons.append("low_lexical_overlap")
            if not chunk_domain and overlap < 0.25:
                reasons.append("chunk_not_in_sports_domain")
        else:
            if score < _MIN_QDRANT_SCORE:
                reasons.append("weak_vector_score")
            if overlap < 0.08 and not chunk_domain:
                reasons.append("low_overlap_no_domain")

        if reasons:
            debug["rejections"].append(
                {
                    "source": c.get("source"),
                    "score": score,
                    "lexical_overlap": round(overlap, 3),
                    "chunk_domain": chunk_domain,
                    "reason": ",".join(reasons),
                }
            )
            continue

        enriched = dict(c)
        enriched["lexical_overlap"] = round(overlap, 3)
        enriched["chunk_domain_match"] = chunk_domain
        accepted.append(enriched)

    accepted.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    accepted = accepted[:top_k]

    debug["accepted_hits_count"] = len(accepted)
    debug["rejected_hits_count"] = len(candidates) - len(accepted)
    if accepted:
        debug["top_score"] = accepted[0].get("score")
        debug["lexical_overlap"] = accepted[0].get("lexical_overlap")
        debug["rejection_reason"] = None
    else:
        debug["rejection_reason"] = "all_candidates_rejected"
        if candidates:
            debug["top_score"] = candidates[0].get("score")

    return accepted, debug

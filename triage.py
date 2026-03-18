"""
AI-powered paper triage.
Uses Claude to score papers on relevance, quality, and timeliness
against the research profile defined in config.py.

Supports two engines:
  - "cli": Uses `claude -p` (Claude Code subscription, no API key needed)
  - "api": Uses the anthropic Python SDK (requires ANTHROPIC_API_KEY)
"""

import json
import re
import subprocess
import sys

import database
from config import ANTHROPIC_API_KEY, RESEARCH_PROFILE, TRIAGE_MODEL


def _build_scoring_prompt(paper: dict) -> str:
    """Build the prompt for Claude to score a single paper."""
    return f"""Score this academic paper for the researcher described below.

{RESEARCH_PROFILE}

---

PAPER TO SCORE:
Title: {paper['title']}
Authors: {paper['authors'] or 'Unknown'}
Journal: {paper['journal'] or 'Unknown'}
Published: {paper['published_date'] or 'Unknown'}
Abstract: {paper['abstract'] or 'No abstract available — score based on title, authors, and journal only.'}

---

Score this paper on three dimensions (each 0-10, integers only):

1. RELEVANCE: How closely does this paper connect to the researcher's three streams?
   0 = completely unrelated, 10 = directly addresses a core research question

2. QUALITY: Based on journal prestige, author reputation signals, and methodological
   indicators in the abstract. Give benefit of the doubt if abstract is missing.
   0 = low-quality venue/methods, 10 = top-tier journal with rigorous methods

3. TIMELINESS: Is this paper responding to a current, active conversation?
   Consider whether it addresses generative AI (very timely), recent policy changes,
   or emerging empirical puzzles.
   0 = settled topic with little new to add, 10 = cutting-edge timing

Respond in this exact JSON format (no markdown, no extra text):
{{"relevance": N, "quality": N, "timeliness": N, "reasoning": "2-3 sentence explanation of scores"}}"""


def _parse_scores(text: str) -> dict | None:
    """Parse JSON scores from model response. Returns None on failure."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting JSON from wrapped response
    match = re.search(r'\{[^}]+\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def _score_via_api(prompt: str) -> str:
    """Score using the anthropic Python SDK."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=TRIAGE_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _score_via_cli(prompt: str) -> str:
    """Score using `claude -p` (Claude Code CLI, no API key needed)."""
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {result.stderr[:200]}")
    return result.stdout


def triage_paper(paper: dict, engine: str = "cli") -> dict | None:
    """
    Score a single paper using Claude.
    Returns the scores dict, or None if scoring failed.
    """
    prompt = _build_scoring_prompt(paper)

    if engine == "api":
        text = _score_via_api(prompt)
    else:
        text = _score_via_cli(prompt)

    scores = _parse_scores(text)
    if scores is None:
        return None

    # Validate expected keys
    for key in ("relevance", "quality", "timeliness"):
        if key not in scores or not isinstance(scores[key], (int, float)):
            return None

    return scores


def run_triage(limit: int = None, engine: str = "cli") -> list[dict]:
    """
    Triage all pending papers in the staging database.
    Returns list of scored papers with their results.
    """
    if engine == "api" and not ANTHROPIC_API_KEY:
        raise ValueError(
            "ANTHROPIC_API_KEY not set. Add it to your .env file, "
            "or use --engine cli to score via Claude Code."
        )

    pending = database.get_pending_papers()
    if not pending:
        print("No pending papers to triage.")
        return []

    if limit:
        pending = pending[:limit]

    print(f"Triaging {len(pending)} papers (engine={engine})...\n")
    results = []

    for i, paper in enumerate(pending, 1):
        title_short = paper["title"][:70] + "..." if len(paper["title"]) > 70 else paper["title"]
        print(f"  [{i}/{len(pending)}] {title_short}")

        try:
            scores = triage_paper(paper, engine=engine)
            if scores is None:
                database.mark_triage_failed(paper["id"], "Failed to parse model response")
                print("           ✗ Failed to parse scores — marked as failed")
                continue

            composite = database.update_triage_scores(
                paper_id=paper["id"],
                relevance=scores["relevance"],
                quality=scores["quality"],
                timeliness=scores["timeliness"],
                reasoning=scores.get("reasoning", ""),
            )
            print(f"           R={scores['relevance']} Q={scores['quality']} "
                  f"T={scores['timeliness']} → {composite:.1f}")
            results.append({**paper, **scores, "composite": composite})

        except Exception as e:
            database.mark_triage_failed(paper["id"], str(e))
            print(f"           ✗ Error: {e}")

    print(f"\nTriaged {len(results)} papers.")
    return results


if __name__ == "__main__":
    engine = "cli"
    limit_val = None
    for arg in sys.argv[1:]:
        if arg.startswith("--engine="):
            engine = arg.split("=", 1)[1]
        else:
            limit_val = int(arg)
    run_triage(limit=limit_val, engine=engine)

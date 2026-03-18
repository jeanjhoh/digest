"""
Generate a weekly digest of top-ranked papers.
Outputs a markdown file with scored papers ranked by composite score.
"""

from datetime import datetime

import database
from database import ALL_STATUSES
from config import DIGEST_DIR, PROMOTE_THRESHOLD


def generate_digest(min_score: float = 0.0, include_pending: bool = False) -> str:
    """
    Generate a markdown digest of papers in the staging database.
    Returns the path to the generated digest file.
    """
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)

    scored = database.get_scored_papers(min_score=min_score)
    pending = database.get_pending_papers() if include_pending else []
    stats = database.get_stats()

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = DIGEST_DIR / f"digest_{date_str}.md"

    lines = []
    lines.append(f"# Paper Digest — {date_str}")
    lines.append("")
    lines.append("## Pipeline Status")
    lines.append("")
    for status in ALL_STATUSES:
        count = stats.get(status, 0)
        lines.append(f"- **{status.capitalize()}**: {count}")
    lines.append("")

    if scored:
        lines.append(f"## Top Papers (score >= {min_score})")
        lines.append("")

        for i, paper in enumerate(scored, 1):
            stars = "★" * int(paper["score_composite"] / 3.4) + "☆" * (3 - int(paper["score_composite"] / 3.4))
            lines.append(f"### {i}. {stars} [{paper['score_composite']:.1f}] {paper['title']}")
            lines.append("")

            if paper["authors"]:
                lines.append(f"**Authors:** {paper['authors']}")
            if paper["journal"]:
                lines.append(f"**Journal:** {paper['journal']}")
            if paper["published_date"]:
                lines.append(f"**Published:** {paper['published_date']}")
            if paper["doi"]:
                lines.append(f"**DOI:** [{paper['doi']}](https://doi.org/{paper['doi']})")

            lines.append("")
            lines.append("| Relevance | Quality | Timeliness |")
            lines.append("|:---------:|:-------:|:----------:|")
            lines.append(f"| {paper['score_relevance']:.0f}/10 | {paper['score_quality']:.0f}/10 | {paper['score_timeliness']:.0f}/10 |")
            lines.append("")

            if paper["triage_reasoning"]:
                lines.append(f"> {paper['triage_reasoning']}")
                lines.append("")

            if paper["abstract"]:
                abstract_short = paper["abstract"][:300]
                if len(paper["abstract"]) > 300:
                    abstract_short += "..."
                lines.append(f"<details><summary>Abstract</summary>\n\n{abstract_short}\n\n</details>")
                lines.append("")

            above_threshold = "ABOVE" if paper["score_composite"] >= PROMOTE_THRESHOLD else "BELOW"
            lines.append(f"*Status: {paper['status']} | {above_threshold} promote threshold*")
            lines.append("")
            lines.append("---")
            lines.append("")

    if pending:
        lines.append(f"## Pending Papers ({len(pending)} awaiting triage)")
        lines.append("")
        for paper in pending[:20]:
            lines.append(f"- **{paper['title']}** — {paper['journal'] or 'Unknown journal'} ({paper['source_channel']})")
        if len(pending) > 20:
            lines.append(f"- ... and {len(pending) - 20} more")
        lines.append("")

    content = "\n".join(lines)

    with open(filename, "w") as f:
        f.write(content)

    print(f"Digest written to: {filename}")
    print(f"  {len(scored)} scored papers, {len(pending)} pending")
    return str(filename)


if __name__ == "__main__":
    generate_digest(include_pending=True)

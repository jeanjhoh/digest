# Weekly Research Digest

A weekly, numbered digest of new papers on entrepreneurship, generative AI and work, and organizations and inequality, published as a static site at <https://jeanjhoh.github.io/digest/> (served under the personal site as `/digest/`). Modeled on Kevin Bryan's [Useful Knowledge](https://kevinbryanecon.com/usefulknowledge).

Each entry shows the paper's original abstract (from Crossref, OpenAlex, Semantic Scholar, or the source), a one-line topical note, links, and a one-click Zotero save via the Zotero Connector.

## How it works

```
GitHub Actions (Wednesday 10:00 UTC)
  fetch sources ─► front-matter filter ─► dedupe / merge versions ─► abstract chain
      └─► keyword gate (free) ─► LLM classification (sets, relevance, note) ─► issue assignment
  commit data/ ─► sitebuilder ─► site/ ─► GitHub Pages
```

- `digest/` — pipeline package (`python -m digest ...`)
- `sitebuilder/` + `web/` — static site generator (`python -m sitebuilder ...`)
- `config/sources.yaml` — the watch list, in three tiers: **A** every paper is classified (top journals), **B** keyword-gated, **C** strict keyword gate
- `config/topics.yaml` — topic sets and keyword gates
- `config/profile.md` — the reader profile the classifier scores against
- `config/settings.yaml` — window, model, thresholds, site metadata
- `data/` — committed state: `articles/<year>.jsonl`, `issues.json`, `runs.jsonl`, and `published/` (the site's input)
- `scripts/google_apps_script.js` — Gmail parser for SSRN / Google Scholar alerts (runs in Google Apps Script, feeds a published Sheet CSV)

## Local use

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # fill in ANTHROPIC_API_KEY, CROSSREF_MAILTO, GSHEET_CSV_URL

python -m digest sources check                     # validate every ISSN / feed
python -m digest run --dry-run --no-llm --days 8   # fetch + keyword stage, print the funnel
python -m digest run --dry-run --llm-limit 1       # one LLM batch, print verdicts
python -m digest run --bootstrap                   # first real run: Issue 1 from a 14-day window
python -m digest publish                           # write data/published/
python -m sitebuilder build --data data/published --out site
python -m sitebuilder check site
python -m sitebuilder serve site                   # http://localhost:8000
python -m pytest
```

Other commands: `python -m digest status`, `python -m digest add-doi <doi>`, `python -m digest fetch --sources asq,jbv --print`.

## Deployment

Repository settings:
- **Pages** → Source: GitHub Actions
- **Secrets**: `ANTHROPIC_API_KEY`, `GSHEET_CSV_URL` (optional `S2_API_KEY`)
- **Variables**: `CROSSREF_MAILTO`, optional `SITE_URL`

`.github/workflows/digest.yml` runs the pipeline weekly, commits `data/`, builds the site, and deploys. Trigger it manually from the Actions tab with `dry_run` to test, or `bootstrap` for the first issue. Pushes to `main` that touch `web/`, `sitebuilder/`, or `data/published/` rebuild and redeploy without re-running the pipeline.

## Editing the watch list

Add or remove entries in `config/sources.yaml` and run `python -m digest sources check`. Tier A means every paper from that venue is sent to the classifier; B and C apply the keyword gate with increasing strictness.

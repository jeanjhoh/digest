# Academic Paper Pipeline

A system that discovers, triages, and surfaces relevant academic papers. Papers flow through a staging database where Claude scores them on relevance to your research before you decide what enters Zotero.

## How It Works

```
Discovery Sources                  Staging DB              Zotero
┌─────────────────┐               ┌──────────┐           ┌──────────────┐
│ OpenAlex API    │──┐            │          │           │              │
│ (16 journals)   │  │  discover  │ pending  │  triage   │  _Reader     │
│                 │  ├──────────→ │    ↓     │─────────→ │   Digest     │
│ Google Scholar  │  │  ingest    │ scored   │  promote  │  collection  │
│ alerts (Gmail)  │──┤            │    ↓     │─────────→ │              │
│                 │  │            │ promoted │           │              │
│ SSRN alerts     │──┤            │ archived │           └──────────────┘
│ (Gmail)         │  │            └──────────┘
│                 │  │
│ Manual DOI      │──┘  capture
└─────────────────┘
```

## Weekly Workflow

A cron job runs **every Friday at 3pm** and does steps 1-4 automatically:

1. `discover` — Fetches new papers from 16 journals via OpenAlex
2. `ingest` — Pulls papers from your Google Sheet (Scholar/SSRN alert emails)
3. `triage` — Claude scores each paper on relevance, quality, and timeliness
4. `digest` — Generates a ranked markdown file in `digests/`
5. **macOS notification** — "Paper Digest Ready"

**What you do:**

- Open `digests/digest_YYYY-MM-DD.md` to scan the ranked list
- Run `python3 cli.py promote --select 1,3,5` to send your picks to Zotero
- When you come across a paper elsewhere, run `python3 cli.py capture <DOI>`

## CLI Reference

```bash
python3 cli.py discover [--days N]       # Fetch new papers from OpenAlex (default: 7 days)
python3 cli.py ingest                    # Import papers from Google Sheet
python3 cli.py capture <DOI>             # Add a paper by DOI (resolves via CrossRef)
python3 cli.py capture --manual          # Add a paper by typing metadata
python3 cli.py triage [--limit N]        # Score pending papers with Claude
python3 cli.py promote                   # Review and send scored papers to Zotero
python3 cli.py promote --select 1,3,5    # Promote specific papers by number
python3 cli.py promote --yes             # Promote all above threshold
python3 cli.py digest                    # Generate markdown digest
python3 cli.py status                    # Show pipeline statistics
```

Triage engine flag: `--engine cli` (default, uses Claude Code) or `--engine api` (uses Anthropic SDK).

## Setup

### 1. Install dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Configure `.env`

```bash
cp .env.example .env
```

Fill in:
- `OPENALEX_EMAIL` — your institutional email (for faster API access)
- `ZOTERO_API_KEY` — from https://www.zotero.org/settings/keys
- `ZOTERO_LIBRARY_ID` — listed as "Your userID" on that page
- `GSHEET_CSV_URL` — your published Google Sheet URL (see below)
- `ANTHROPIC_API_KEY` — only needed if using `--engine api`

### 3. Google Apps Script (for Scholar/SSRN email ingestion)

1. Create a Google Sheet named "Paper Pipeline Inbox"
2. Extensions → Apps Script → paste contents of `google_apps_script.js`
3. Run `processAlerts` once and authorize
4. Add a daily trigger (Triggers → Add → Time-driven → Day timer)
5. File → Share → Publish to web → Sheet1 → CSV → copy URL into `.env`

### 4. Gmail filters (keep inbox clean)

Create two filters to auto-archive alert emails:
- From `scholaralerts-noreply@google.com` → Skip Inbox, label `Papers/Scholar`
- From `SSRN@email.ssrn.com OR noreply@ssrn.com` → Skip Inbox, label `Papers/SSRN`

### 5. Zotero RSS feeds

Add journal RSS feeds in Zotero (File → New Feed → From URL). See the project setup notes for verified feed URLs.

## Configuration

Edit `config.py` to customize:
- `TARGET_JOURNALS` — journals to monitor (with OpenAlex source IDs)
- `RESEARCH_PROFILE` — your research description (used for triage scoring)
- `PROMOTE_THRESHOLD` — minimum score to suggest promotion (default: 7.0)
- `READING_QUEUE_CAP` — max papers in reading queue (default: 15)
- `TRIAGE_MODEL` — Claude model for scoring
- `DISCOVERY_LOOKBACK_DAYS` — how far back to search (default: 7)

## File Structure

```
reader/
├── cli.py              # Unified CLI entry point
├── config.py           # Research profile, journals, settings
├── database.py         # SQLite staging database
├── discover.py         # OpenAlex journal discovery
├── ingest.py           # Google Sheet ingestion
├── capture.py          # Manual DOI/title capture
├── triage.py           # Claude-powered scoring
├── promote.py          # Zotero promotion
├── digest.py           # Markdown digest generator
├── run_weekly.sh       # Cron automation script
├── google_apps_script.js  # Gmail parser (paste into Apps Script)
├── requirements.txt
├── .env                # Your API keys (not tracked)
├── data/papers.db      # Staging database
└── digests/            # Generated digests
```

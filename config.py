"""
Configuration for the academic paper pipeline.
Research profile, target journals, and settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# --- Paths ---
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "papers.db"
DIGEST_DIR = BASE_DIR / "digests"

# --- API Keys (from environment) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ZOTERO_API_KEY = os.getenv("ZOTERO_API_KEY", "")
ZOTERO_LIBRARY_ID = os.getenv("ZOTERO_LIBRARY_ID", "")
ZOTERO_LIBRARY_TYPE = os.getenv("ZOTERO_LIBRARY_TYPE", "user")  # "user" or "group"
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "")  # For polite pool access
GSHEET_CSV_URL = os.getenv("GSHEET_CSV_URL", "")  # Published Google Sheet CSV for email alert ingestion

# --- Research Profile (used by triage to score relevance) ---
RESEARCH_PROFILE = """
You are scoring papers for an assistant professor of Organizational Theory & Entrepreneurship
at Carnegie Mellon University's Tepper School of Business.

Research streams (score higher for papers touching these):

1. SOCIOECONOMIC ORIGINS & ENTREPRENEURSHIP: How class background, socioeconomic origins,
   and social stratification shape entrepreneurial outcomes. Includes VC funding disparities,
   founder demographics, and how privilege/disadvantage affect startup trajectories.

2. SOCIAL ENTREPRENEURSHIP MOTIVATION: What motivates entrepreneurs to engage with pressing
   social problems (climate, inequality, health). Prosocial motivation, hybrid organizations,
   social ventures, impact investing.

3. GENERATIVE AI & ENTREPRENEURSHIP/LABOR: How generative AI (LLMs, foundation models)
   reshapes entrepreneurship and labor markets. AI-augmented ideation, displacement effects,
   new venture creation with AI, future of work.

Methodological interests (slight bonus):
- Regression analyses on archival data
- Lab-in-the-field experiments
- Digital field experiments
- Causal identification strategies

Score LOWER for papers that are:
- Pure theoretical without empirical contribution
- In unrelated fields (hard sciences, medicine, engineering)
- Purely methodological with no substantive application
- Conference proceedings or workshop papers (prefer journal articles)
"""

# --- Target Journals (OpenAlex source IDs) ---
# These are queried weekly by the discover module.
# Format: (display_name, openalex_source_id)
# To find source IDs: https://api.openalex.org/sources?search=journal+name
TARGET_JOURNALS = [
    # --- Management & Entrepreneurship ---
    ("Administrative Science Quarterly", "S143668711"),
    ("Academy of Management Journal", "S117778295"),
    ("Academy of Management Review", "S46763546"),
    ("Strategic Management Journal", "S102949365"),
    ("Management Science", "S33323087"),
    ("Organization Science", "S206124708"),
    ("Research Policy", "S9731383"),
    ("Entrepreneurship Theory and Practice", "S187626162"),
    ("Journal of Business Venturing", "S66201313"),
    # --- Sociology ---
    ("American Sociological Review", "S157620343"),
    ("American Journal of Sociology", "S122471516"),
    ("Social Forces", "S130611943"),
    # --- Economics ---
    ("American Economic Review", "S23254222"),
    ("Quarterly Journal of Economics", "S203860005"),
    ("Journal of Economic Perspectives", "S72880728"),
    # --- Interdisciplinary ---
    ("Nature Human Behaviour", "S2764866340"),
]

# --- Triage Settings ---
TRIAGE_MODEL = "claude-sonnet-4-20250514"  # Cost-effective for scoring
PROMOTE_THRESHOLD = 7.0  # Minimum composite score (avg of 3 dimensions) to suggest promotion
READING_QUEUE_CAP = 15  # Max papers in reading queue

# --- Discovery Settings ---
DISCOVERY_LOOKBACK_DAYS = 7  # How far back to look for new papers
OPENALEX_RATE_LIMIT = 0.15  # Seconds between requests (stay under 10/sec)

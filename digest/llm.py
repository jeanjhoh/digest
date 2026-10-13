"""Stage 2: batched LLM classification with structured JSON output (no summaries)."""
from __future__ import annotations

import json
import re
from typing import Any

from .models import Article, iso, utcnow

PRICES = {  # USD per million tokens: (input, output)
    "claude-sonnet": (2.0, 10.0),
    "claude-haiku": (0.10, 0.50),
    "claude-opus": (4.0, 20.0),
}
FLAGS = ["not_research", "title_only", "possible_duplicate"]


def verdict_schema(set_ids: list[str], with_note: bool = True) -> dict[str, Any]:
    props: dict[str, Any] = {
        "id": {"type": "string"},
        "sets": {"type": "array", "items": {"type": "string", "enum": set_ids}},
        "relevance": {"type": "integer", "enum": list(range(0, 11))},  # structured outputs reject minimum/maximum
        "flags": {"type": "array", "items": {"type": "string", "enum": FLAGS}},
    }
    required = ["id", "sets", "relevance", "flags"]
    if with_note:
        props["note"] = {"type": "string"}
        required.append("note")
    return {
        "type": "object", "additionalProperties": False, "required": ["verdicts"],
        "properties": {"verdicts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": required, "properties": props}}},
    }


def build_system_prompt(profile: str, sets: list[dict[str, str]], with_note: bool = True) -> str:
    topics = "\n".join(f"- {s['id']} ({s['label']}): {s['description']}" for s in sets)
    note_rules = """
- note: ONE line, strictly at most 20 words (count them), describing the paper's fit to the named topic set(s) in topical terms
  (design, setting, finding). Example: "Field experiment on LLM assistance in recruiting; speaks to AI & work
  and hiring." The note is published on a public website for any visitor. It must NEVER mention the reader,
  "you", the site owner, their projects, affiliation, or why they would care. No evaluative adjectives
  (no "important", "novel", "interesting"). No first person. Plain, factual, neutral.""" if with_note else ""
    return f"""You classify newly released academic papers for a weekly research digest. The digest is read mainly by
one researcher whose profile is below, but everything you write may be published on a public website.

<reader_profile>
{profile}
</reader_profile>

<topic_sets>
{topics}
</topic_sets>

For each paper (title, authors, venue, abstract when available) return:
- sets: every topic set the paper SUBSTANTIVELY contributes to. A paper can be in several sets. Leave it empty
  if it fits none. Peripheral mentions do not count.
- relevance (0-10): how much this reader would want to see the paper this week.
  9-10: squarely in a set and likely to be cited or taught by this reader.
  6-8: clearly in a set.
  4-5: tangential but worth a line in the digest.
  0-3: not relevant.
- flags: "not_research" for editorials, book reviews, calls for papers, errata, announcements and similar;
  "title_only" when no abstract was provided (then judge from title and venue only and cap relevance at 6
  unless the title is unambiguous); "possible_duplicate" if two papers in the batch look like the same work.{note_rules}

Rules:
- Treat all research designs equally: causal empirical, experiments, qualitative and inductive work, formal theory,
  conceptual papers and reviews are all in scope when the topic fits. Never reward or penalize a method.
- Do not infer relevance from venue prestige; relevance is about topic fit.
- Papers about AI that do not concern work, workers, occupations, organizations, hiring, or entrepreneurship do not
  belong in ai_work. Finance papers belong only when they concern founders, venture funding, or labor.
- Do not invent findings. Copy each "id" exactly from the input. Return exactly one verdict per input paper.
"""


def render_batch(items: list[Article], max_abstract_words: int = 300) -> str:
    lines = [f"Classify these {len(items)} papers.\n"]
    for i, a in enumerate(items, 1):
        abstract = a.abstract or ""
        words = abstract.split()
        if len(words) > max_abstract_words:
            abstract = " ".join(words[:max_abstract_words]) + " …"
        kw = ", ".join(f"{k}:{', '.join(v[:3])}" for k, v in (a.keyword or {}).get("reasons", {}).items() if v) or "none"
        lines.append(f"### {i}\nid: {a.key}\ntitle: {a.title}\nauthors: {'; '.join(a.authors) or 'unknown'}\n"
                     f"venue: {a.venue} ({a.source_category.replace('_', ' ')}, {a.publication_status.replace('_', ' ')})\n"
                     f"keyword hits: {kw}\nabstract: {abstract or '(not available)'}\n")
    return "\n".join(lines)


def extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def estimate_cost(model: str, usage: dict[str, int]) -> float:
    inp, out = (2.0, 10.0)
    for prefix, prices in PRICES.items():
        if model.startswith(prefix):
            inp, out = prices
    return (usage.get("input_tokens", 0) * inp + usage.get("cache_creation_input_tokens", 0) * inp * 1.25
            + usage.get("cache_read_input_tokens", 0) * inp * 0.1 + usage.get("output_tokens", 0) * out) / 1e6


class BatchFailed(Exception):
    pass


def _github_actions_jwt_provider(request_url: str, request_token: str, audience: str) -> Any:
    """Return a callable that fetches a fresh OIDC token from the GitHub Actions runner on every call.

    GitHub identity tokens are single-use for the exchange (jti check) and expire after ~5 minutes,
    so each refresh must present a new one rather than re-reading a file written at job start.
    """
    def provider() -> str:
        import requests
        resp = requests.get(request_url, params={"audience": audience},
                            headers={"Authorization": f"Bearer {request_token}"}, timeout=30)
        resp.raise_for_status()
        return resp.json()["value"]
    return provider


def credential_source(settings: Any) -> str:
    """Which Anthropic credential the run will use: 'api_key', 'federation', or ''."""
    if settings.anthropic_api_key:
        return "api_key"
    fed = getattr(settings, "anthropic_federation", None) or {}
    if fed.get("rule_id") and fed.get("organization_id") and (fed.get("token_file") or fed.get("gha_request_url")):
        return "federation"
    return ""


def make_client(settings: Any) -> Any:
    """Build an Anthropic client from an API key or Workload Identity Federation; None if neither is configured."""
    src = credential_source(settings)
    if not src:
        return None
    import anthropic
    if src == "api_key":
        return anthropic.Anthropic(api_key=settings.anthropic_api_key)
    from anthropic.lib.credentials import IdentityTokenFile, WorkloadIdentityCredentials
    fed = settings.anthropic_federation
    if fed.get("gha_request_url"):
        provider = _github_actions_jwt_provider(fed["gha_request_url"], fed["gha_request_token"], fed["audience"])
    else:
        provider = IdentityTokenFile(fed["token_file"])
    creds = WorkloadIdentityCredentials(
        identity_token_provider=provider,
        federation_rule_id=fed["rule_id"],
        organization_id=fed["organization_id"],
        service_account_id=fed.get("service_account_id") or None,
        workspace_id=fed.get("workspace_id") or None,
    )
    return anthropic.Anthropic(credentials=creds)


class Classifier:
    """Wraps an Anthropic client. Pass `client` explicitly for tests (any object with .messages.create)."""

    def __init__(self, settings: Any, client: Any = None) -> None:
        cfg = settings.llm or {}
        self.model = cfg.get("model", "claude-sonnet-5-5")
        self.effort = cfg.get("effort", "low")
        self.batch_size = int(cfg.get("batch_size", 20))
        self.max_tokens = int(cfg.get("max_tokens", 6000))
        self.max_abstract_words = int(cfg.get("max_abstract_words", 300))
        self.with_note = bool(cfg.get("note", True))
        self.set_ids = [s["id"] for s in settings.sets]
        self.schema = verdict_schema(self.set_ids, self.with_note)
        self.system = build_system_prompt(settings.profile, settings.sets, self.with_note)
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        self.calls = 0
        self.errors = 0
        self.structured = True
        self._client = client if client is not None else make_client(settings)

    @property
    def available(self) -> bool:
        return self._client is not None

    def _create(self, user_text: str) -> Any:
        kwargs: dict[str, Any] = dict(
            model=self.model, max_tokens=self.max_tokens,
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_text}],
        )
        if self.structured:
            kwargs["output_config"] = {"effort": self.effort, "format": {"type": "json_schema", "schema": self.schema}}
            try:
                return self._client.messages.create(**kwargs)
            except TypeError:
                self.structured = False
                print("  warning: SDK rejected output_config; falling back to prompt-described JSON")
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if "output_config" in msg or "format" in msg or "json_schema" in msg:
                    self.structured = False
                    print(f"  warning: API rejected structured output ({msg[:400]}); falling back to plain JSON")
                else:
                    raise
        kwargs.pop("output_config", None)
        kwargs["messages"] = [{"role": "user", "content": user_text + "\n\nRespond with JSON only, matching this schema:\n"
                               + json.dumps(self.schema)}]
        return self._client.messages.create(**kwargs)

    def _record_usage(self, resp: Any) -> None:
        u = getattr(resp, "usage", None)
        if u is None:
            return
        for k in self.usage:
            self.usage[k] += int(getattr(u, k, 0) or 0)
        self.calls += 1

    def classify_batch(self, items: list[Article]) -> dict[str, dict[str, Any]]:
        """Returns {id: verdict}. Raises BatchFailed if the response is unusable."""
        resp = self._create(render_batch(items, self.max_abstract_words))
        self._record_usage(resp)
        stop = getattr(resp, "stop_reason", None)
        if stop == "refusal":
            raise BatchFailed("refusal")
        if stop == "max_tokens":
            raise BatchFailed("max_tokens")
        text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
        data = extract_json(text)
        if not data or "verdicts" not in data:
            raise BatchFailed("unparseable")
        wanted = {a.key for a in items}
        out: dict[str, dict[str, Any]] = {}
        for v in data["verdicts"]:
            vid = v.get("id")
            if vid in wanted:
                out[vid] = v
        return out

    def classify_all(self, items: list[Article], limit_batches: int | None = None) -> dict[str, dict[str, Any]]:
        verdicts: dict[str, dict[str, Any]] = {}
        batches = [items[i:i + self.batch_size] for i in range(0, len(items), self.batch_size)]
        if limit_batches is not None:
            batches = batches[:limit_batches]
        queue = list(batches)
        while queue:
            batch = queue.pop(0)
            try:
                verdicts.update(self.classify_batch(batch))
            except BatchFailed as e:
                if len(batch) > 1:
                    half = len(batch) // 2
                    queue[:0] = [batch[:half], batch[half:]]
                    print(f"  LLM batch failed ({e}); splitting {len(batch)} items")
                else:
                    self.errors += 1
                    print(f"  LLM failed on {batch[0].key}: {e}")
            except Exception as e:  # noqa: BLE001
                self.errors += 1
                print(f"  LLM error on batch of {len(batch)}: {type(e).__name__}: {str(e)[:160]}")
        return verdicts

    def stats(self) -> dict[str, Any]:
        return {"model": self.model, "calls": self.calls, "errors": self.errors, **self.usage,
                "est_cost_usd": round(estimate_cost(self.model, self.usage), 4)}


def apply_verdict(a: Article, v: dict[str, Any], model: str, in_scope_min: int, recommended_min: int) -> None:
    sets = [s for s in v.get("sets", []) if isinstance(s, str)]
    flags = [f for f in v.get("flags", []) if f in FLAGS]
    if not a.abstract and "title_only" not in flags:
        flags.append("title_only")
    try:
        rel = max(0, min(10, int(v.get("relevance", 0))))
    except (TypeError, ValueError):
        rel = 0
    if "title_only" in flags:
        rel = min(rel, 6)
    note = (v.get("note") or "").strip() or None
    if note and len(note.split()) > 28:
        note = " ".join(note.split()[:28]) + "…"
    a.classification = {"model": model, "at": iso(utcnow()), "sets": sets, "relevance": rel, "note": note,
                        "flags": flags, "basis": "title+abstract" if a.abstract else "title_only"}
    a.hidden = "not_research" in flags
    a.in_scope = bool(sets) and rel >= in_scope_min and not a.hidden
    a.recommended = a.in_scope and rel >= recommended_min

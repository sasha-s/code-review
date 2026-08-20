"""Join parsed findings to observed outcomes.

ANALYSIS ONLY — see outcome-ledger/README.md.

Signal strength is explicit and never collapsed:

  STRONG   the reviewer re-verified the finding against a later head in a later
           round and recorded a terminal status in the cumulative ledger, or a
           human comment on the PR names the finding's ledger id.
  MEDIUM   a human replied on the PR after our comment was posted, or reacted
           to it. PR-level, not finding-level: it says someone engaged, not
           that they engaged with THIS finding.
  WEAK     files the finding points at changed in commits pushed after the
           review, and/or the PR reached a terminal state. Circumstantial.
           "File changed after review" is NOT evidence the finding was accepted.
  NONE     the PR was reviewed once and never re-reviewed; nothing observable
           says whether the finding was right or acted on.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

BOT_SIGNATURE = "Codex on behalf of Sasha"
# The account the watcher posts from. Comments from this login that are NOT the
# watcher's own posts are the review OPERATOR writing by hand (typically a
# per-finding disposition). They are human, but they are our side of the
# conversation - never counted as the PR author engaging with a finding.
OPERATOR_LOGIN = "sasha-s"
KNOWN_BOTS = ("coderabbitai", "github-actions", "dependabot", "codecov",
              "vercel", "sonarcloud", "netlify", "sentry-io", "graphite-app",
              "greptile", "linear", "cursor", "ellipsis", "sweep-ai")


def parse_iso(s):
    if not s:
        return None
    try:
        return datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except ValueError:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except (ValueError, AttributeError):
            return None


def is_our_comment(c: dict, posted_urls: set) -> bool:
    return BOT_SIGNATURE in (c.get("body") or "") or c.get("html_url") in posted_urls


def is_bot(c: dict) -> bool:
    u = (c.get("user") or "").lower()
    return c.get("user_type") == "Bot" or any(b in u for b in KNOWN_BOTS)


def pr_engagement(bundle: dict, posted_urls: set) -> dict:
    comments = bundle.get("comments") or []
    ours = [c for c in comments if is_our_comment(c, posted_urls)]
    humans = [c for c in comments if not is_our_comment(c, posted_urls) and not is_bot(c)]
    author = (bundle.get("pr") or {}).get("author")
    operator = [c for c in humans if c.get("user") == OPERATOR_LOGIN]
    counterparty = [c for c in humans if c.get("user") != OPERATOR_LOGIN]
    return {
        "our_comments": ours,
        "human_comments": humans,
        "operator_comments": operator,
        "counterparty_comments": counterparty,
        "author_comments": [c for c in counterparty if c.get("user") == author],
        "reactions_on_ours": sum(c.get("reactions_total", 0) for c in ours),
        "reaction_kinds": _merge_reactions(ours),
        "human_reviews": [r for r in (bundle.get("reviews") or [])
                          if r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED")
                          and not (r.get("user") or "").lower().endswith("[bot]")],
        "review_comments": bundle.get("review_comments") or [],
    }


def _merge_reactions(cs: list) -> dict:
    out: dict = {}
    for c in cs:
        for k, v in (c.get("reactions") or {}).items():
            out[k] = out.get(k, 0) + v
    return out


def churn_after(bundle: dict, since_ts: float, commit_files: dict) -> tuple[set, int, int]:
    """Files touched by PR commits pushed after `since_ts`."""
    touched: set = set()
    n_after, n_unresolved = 0, 0
    for c in bundle.get("commits") or []:
        ts = parse_iso(c.get("committer_date") or c.get("author_date"))
        if ts is None or since_ts is None or ts <= since_ts:
            continue
        n_after += 1
        files = commit_files.get(c["sha"])
        if files is None:
            n_unresolved += 1
            continue
        touched.update(files)
    return touched, n_after, n_unresolved


ID_MENTION_CACHE: dict = {}


def id_mentioned(ledger_id: str, comments: list, since_ts: float) -> list:
    pat = re.compile(rf"(?<![A-Za-z0-9]){re.escape(ledger_id)}(?![A-Za-z0-9])")
    hits = []
    for c in comments:
        ts = parse_iso(c.get("created_at"))
        if since_ts is not None and ts is not None and ts <= since_ts:
            continue
        if pat.search(c.get("body") or ""):
            hits.append(c.get("html_url"))
    return hits


LABEL_FROM_STATUS = {
    "resolved": "acted_on",
    "partially_resolved": "partially_acted_on",
    "open": "not_acted_on",
    "rejected": "retracted_by_reviewer",
    "obsolete": "obsolete",
}


def label_finding(f: dict, bundle: dict, eng: dict, commit_files: dict) -> dict:
    pr = bundle.get("pr") or {}
    since = parse_iso(f.get("first_posted_at")) or parse_iso(f.get("first_seen_at"))
    # A strong label needs the reviewer to have re-checked the finding against a
    # LATER head. When the status names the round that settled it, trust that
    # round; a status re-stated in the round that first raised it is a
    # carry-forward, not a verification.
    cited = _status_cited_round(f)
    if f["final_status"] in ("rejected", "obsolete"):
        # A retraction is a terminal reviewer judgment about the claim itself
        # ("this was never a real finding"), so it does not need a later head to
        # be meaningful - unlike "resolved", which asserts the author changed code.
        verified = True
    elif cited is not None:
        verified = cited > f["first_round"]
    else:
        verified = f["last_round"] > f["first_round"]

    touched, n_commits_after, n_unresolved = churn_after(bundle, since, commit_files)
    ref_paths = [r["path"] for r in f.get("refs") or []]
    ref_hits = sorted(p for p in ref_paths if p in touched)

    def after(cs):
        return [c for c in cs
                if since is None or (parse_iso(c.get("created_at")) or 0) > since]

    counterparty_after = after(eng["counterparty_comments"])
    operator_after = after(eng["operator_comments"])
    human_after = counterparty_after + operator_after
    real_id = bool(re.match(r"^[A-Z]{1,3}\d+$", f["ledger_id"]))
    id_hits = id_mentioned(f["ledger_id"], eng["counterparty_comments"], since) if real_id else []
    operator_id_hits = id_mentioned(f["ledger_id"], eng["operator_comments"], since) if real_id else []

    inline_hits = [c for c in eng["review_comments"]
                   if c.get("path") in set(ref_paths)
                   and (since is None or (parse_iso(c.get("created_at")) or 0) > since)]

    if verified and f["final_status"] in LABEL_FROM_STATUS:
        outcome = LABEL_FROM_STATUS[f["final_status"]]
        strength = "strong"
        if f["final_status"] in ("rejected", "obsolete"):
            basis = (f"reviewer retracted the finding (raised r{f['first_round']}): "
                     f"{f['final_status_raw'][:160]}")
        else:
            basis = (f"reviewer re-verified in round {cited or f['last_round']} "
                     f"(first raised r{f['first_round']}): {f['final_status_raw'][:160]}")
    elif id_hits:
        outcome = "human_engaged"
        strength = "strong"
        basis = f"a non-operator human comment names {f['ledger_id']}: {id_hits[0]}"
    else:
        outcome = "unlabeled"
        if operator_id_hits:
            strength, basis = "medium", (
                f"the review operator posted a disposition naming {f['ledger_id']} "
                f"({operator_id_hits[0]}), but the reviewer never re-verified it "
                f"against a later head")
        elif counterparty_after:
            strength, basis = "medium", (
                f"{len(counterparty_after)} comment(s) from the PR author or another "
                f"human after the review, none naming {f['ledger_id']}")
        elif operator_after:
            strength, basis = "medium", (
                f"{len(operator_after)} operator comment(s) after the review, "
                f"none naming {f['ledger_id']}")
        elif eng["reactions_on_ours"]:
            strength, basis = "medium", f"{eng['reactions_on_ours']} reaction(s) on our comment(s)"
        elif ref_hits:
            strength, basis = "weak", f"{len(ref_hits)}/{len(ref_paths)} cited file(s) changed in {n_commits_after} commit(s) pushed after the review"
        elif n_commits_after:
            strength, basis = "weak", f"{n_commits_after} commit(s) after the review, none touching the cited files"
        elif pr.get("merged"):
            strength, basis = "weak", "PR merged with no further commits after the review"
        else:
            strength, basis = "none", "single review round, no post-review commits, no human reply"

    return {
        "outcome": outcome,
        "outcome_strength": strength,
        "outcome_basis": basis,
        "reviewer_verified": verified,
        "signals": {
            "pr_state": "merged" if pr.get("merged") else ("closed_unmerged" if pr.get("state") == "closed" else "open"),
            "pr_merged_at": pr.get("merged_at"),
            "merged_after_review": bool(pr.get("merged_at") and since and (parse_iso(pr["merged_at"]) or 0) > since),
            "commits_after_review": n_commits_after,
            "commits_after_review_unresolved_locally": n_unresolved,
            "cited_files": ref_paths,
            "cited_files_touched_after_review": ref_hits,
            "human_comments_after_review": len(human_after),
            "counterparty_comments_after_review": len(counterparty_after),
            "operator_comments_after_review": len(operator_after),
            "counterparty_comment_urls": [c.get("html_url") for c in counterparty_after][:5],
            "author_replied_after_review": any(
                c.get("user") == pr.get("author") for c in counterparty_after),
            "ledger_id_named_in_operator_disposition": operator_id_hits,
            "reactions_on_our_comments": eng["reactions_on_ours"],
            "reaction_kinds": eng["reaction_kinds"],
            "ledger_id_mentioned_by_human": id_hits,
            "inline_review_comments_on_cited_files": len(inline_hits),
            "human_review_states": sorted({r["state"] for r in eng["human_reviews"]}),
        },
    }


def _status_cited_round(f: dict) -> int | None:
    m = re.search(r"\br(\d+)\b", (f.get("final_status_raw") or "").lower())
    return int(m.group(1)) if m else None

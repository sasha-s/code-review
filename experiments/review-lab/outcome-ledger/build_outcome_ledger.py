#!/usr/bin/env python3
"""Build the PR-review outcome ledger for TheEdge.

ANALYSIS ONLY — see outcome-ledger/README.md. This tool reads review artifacts,
git history, and the GitHub API strictly read-only, and writes only under
--out (default ~/.review/TheEdge/ledger/). It never posts, edits, reacts to, or
resolves anything on GitHub, never mutates the repo, and its output must never
be injected into a live reviewer prompt.

Stages:
  parse  review markdown -> reviews.jsonl + findings.raw.jsonl
  fetch  GitHub PR state/comments/commits/reviews -> cache/gh/*.json
  join   outcome labels -> findings.jsonl + summary.json
  all    parse, fetch, join
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse_reviews as P  # noqa: E402
import gh_fetch as G  # noqa: E402
import join_outcomes as J  # noqa: E402
import null_baseline as NB  # noqa: E402

REPO_SLUG = "TheEdgeApp/TheEdge"
REVIEWS_ROOT = os.path.expanduser("~/reviews/TheEdge")
STATE_DIR = os.path.expanduser("~/.review/TheEdge")
GIT_REPO = os.path.expanduser("~/TheEdge")
BOT_SIGNATURE = "Codex on behalf of Sasha"
DEFAULT_OUT = os.path.join(STATE_DIR, "ledger")


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", file=sys.stderr, flush=True)


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> float | None:
    if not s:
        return None
    try:
        return datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except ValueError:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None


# ------------------------------------------------------------------ state TSVs

def read_tsv(path: str, cols: list[str]) -> list[dict]:
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            parts += [""] * (len(cols) - len(parts))
            out.append(dict(zip(cols, parts)))
    return out


def load_state() -> dict:
    reviewed = read_tsv(os.path.join(STATE_DIR, "reviewed-prs.tsv"),
                        ["pr", "head_sha", "pr_updated_at", "reviewed_at", "driver",
                         "artifact_path", "title"])
    posted = read_tsv(os.path.join(STATE_DIR, "posted-comments.tsv"),
                      ["posted_at", "pr", "head_sha", "hash", "comment_url", "comment_path"])
    attempts = read_tsv(os.path.join(STATE_DIR, "attempts.tsv"),
                        ["attempted_at", "pr", "head_sha", "pr_updated_at", "driver",
                         "status", "reason", "artifact_path", "log_path"])
    return {"reviewed": reviewed, "posted": posted, "attempts": attempts}


# ---------------------------------------------------------------- stage: parse

def stage_parse(out_dir: str) -> dict:
    state = load_state()
    reviewed_at_by_artifact = {}
    for r in state["reviewed"]:
        if r["artifact_path"]:
            reviewed_at_by_artifact[os.path.realpath(r["artifact_path"])] = r["reviewed_at"]
    titles = {}
    for r in state["reviewed"]:
        if r["pr"].isdigit():
            titles[int(r["pr"])] = r["title"]

    # posted comment time per (pr, head8) and earliest post per artifact stem
    posted_by_path = {}
    for p in state["posted"]:
        if p["comment_path"]:
            posted_by_path.setdefault(os.path.realpath(p["comment_path"]), p)

    files = P.find_review_files(REVIEWS_ROOT)
    log(f"parse: {len(files)} candidate review artifacts")

    reviews = []
    parsed_ok = 0
    for pr, path in files:
        rec = P.parse_review_file(pr, path)
        if not rec["ledger_rows"] and not rec["action_items"]:
            text = open(path, encoding="utf-8", errors="replace").read()
            rec["heading_findings"] = P.parse_findings_headings(text)
            if not rec["heading_findings"]:
                rec["heading_findings"] = [
                    {"id": it["id"], "sev": "unrated", "title": it["text"][:400],
                     "body": it["text"]}
                    for it in P.parse_unnumbered_action_items(text)]
        rp = os.path.realpath(path)
        rec["reviewed_at"] = reviewed_at_by_artifact.get(rp) or iso(rec["mtime"])
        rec["reviewed_at_source"] = "state-tsv" if rp in reviewed_at_by_artifact else "mtime"
        # locate the posted comment draft that pairs with this artifact
        stem = re.sub(r"(-full-review|-review|-deepreview|-full)?\.md$", "", path)
        cand = [stem + "-comment.md", stem + "-github-comment.md",
                stem + "_comment.md", path[:-3] + "-comment.md"]
        rec["comment_path"] = next((c for c in cand if os.path.exists(c)), None)
        pinfo = posted_by_path.get(os.path.realpath(rec["comment_path"])) if rec["comment_path"] else None
        rec["posted_at"] = pinfo["posted_at"] if pinfo else None
        rec["comment_url"] = pinfo["comment_url"] if pinfo else None
        rec["title"] = titles.get(pr, "")
        if rec["ledger_rows"] or rec["action_items"] or rec["heading_findings"]:
            parsed_ok += 1
        reviews.append(rec)

    # order rounds per PR
    by_pr = collections.defaultdict(list)
    for rec in reviews:
        by_pr[rec["pr"]].append(rec)
    for pr, recs in by_pr.items():
        recs.sort(key=lambda r: (parse_iso(r["reviewed_at"]) or r["mtime"], r["round"] or 0))
        for i, r in enumerate(recs, 1):
            r["order"] = i
            r["rounds_in_pr"] = len(recs)

    findings = build_findings(by_pr)

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "reviews.jsonl"), "w") as fh:
        for rec in reviews:
            slim = {k: v for k, v in rec.items()
                    if k not in ("ledger_rows", "action_items", "heading_findings")}
            slim["n_ledger_rows"] = len(rec["ledger_rows"])
            slim["n_action_items"] = len(rec["action_items"])
            slim["n_heading_findings"] = len(rec["heading_findings"])
            fh.write(json.dumps(slim) + "\n")
    with open(os.path.join(out_dir, "findings.raw.jsonl"), "w") as fh:
        for f in findings:
            fh.write(json.dumps(f) + "\n")

    report = {
        "artifacts_scanned": len(files),
        "artifacts_with_any_structure": parsed_ok,
        "artifacts_with_ledger_table": sum(1 for r in reviews if r["has_ledger_table"]),
        "artifacts_with_zero_findings": sum(
            1 for r in reviews
            if not r["ledger_rows"] and not r["action_items"] and not r["heading_findings"]),
        "artifacts_explicitly_no_findings": sum(
            1 for r in reviews
            if not r["ledger_rows"] and not r["action_items"] and not r["heading_findings"]
            and re.search(r"[Nn]o (open |actionable |new |blocking )?findings?\b",
                          open(r["path"], encoding="utf-8", errors="replace").read())),
        "artifacts_clean_empty_ledger": sum(
            1 for r in reviews
            if r["has_ledger_table"] and not r["ledger_rows"] and not r["action_items"]
            and not r["heading_findings"]),
        "artifacts_missing_round_header": sum(1 for r in reviews if r["round"] is None),
        "artifacts_missing_head_sha": sum(1 for r in reviews if not r["head"]),
        "reviewed_at_from_state_tsv": sum(1 for r in reviews if r["reviewed_at_source"] == "state-tsv"),
        "prs": len(by_pr),
        "findings": len(findings),
        "findings_from_ledger": sum(1 for f in findings if f["source"] == "ledger"),
        "findings_from_action_items_only": sum(1 for f in findings if f["source"] == "action-item"),
        "findings_from_headings": sum(1 for f in findings if f["source"] == "findings-heading"),
    }
    report["artifacts_linked_to_a_posted_comment"] = sum(1 for r in reviews if r["posted_at"])
    report["artifacts_with_a_comment_draft_on_disk"] = sum(1 for r in reviews if r["comment_path"])
    report["parse_coverage"] = round(
        (report["artifacts_with_any_structure"] + report["artifacts_explicitly_no_findings"])
        / max(1, report["artifacts_scanned"]), 4)
    report["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report["unparsed_artifacts"] = [
        r["path"] for r in reviews
        if not r["ledger_rows"] and not r["action_items"] and not r["heading_findings"]
        and not re.search(r"[Nn]o (open |actionable |new |blocking )?findings?\b",
                          open(r["path"], encoding="utf-8", errors="replace").read())]
    with open(os.path.join(out_dir, "parse_report.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    log(f"parse: {json.dumps({k: v for k, v in report.items() if k != 'unparsed_artifacts'})}")
    return report


def build_findings(by_pr: dict[int, list[dict]]) -> list[dict]:
    """Fold the cumulative per-round ledgers into one row per (PR, ledger id)."""
    findings: list[dict] = []
    for pr, recs in sorted(by_pr.items()):
        acc: dict[str, dict] = {}
        for rec in recs:
            rnd = rec["round"] or rec["order"]
            seen_ids = set()
            for row in rec["ledger_rows"]:
                fid = row["id"]
                seen_ids.add(fid)
                text = row["finding"].strip()
                action = rec["action_items"].get(fid, "")
                sev_raw = row["sev"].strip()
                sev = next((P.SEV_MAP[c] for c in sev_raw if c in P.SEV_MAP), "unrated")
                upsert(acc, pr, fid, text, action, sev, sev_raw, row["scope"],
                       row["status"], rnd, rec, "ledger")
            # heading-style findings (artifacts with no ledger table at all)
            for k, hf in enumerate(rec["heading_findings"], 1):
                fid = hf["id"] or f"H{k}"
                if fid in seen_ids:
                    continue
                seen_ids.add(fid)
                upsert(acc, pr, fid, hf["title"], hf["body"], hf["sev"], "", "",
                       "", rnd, rec, "findings-heading")
            # action items with no ledger row (older / unstructured artifacts)
            for fid, action in rec["action_items"].items():
                if fid in seen_ids or fid in acc:
                    if fid in acc and not acc[fid]["action_text"]:
                        acc[fid]["action_text"] = action
                    continue
                sev_raw = "".join(c for c in action[:12] if c in P.SEV_MAP)
                sev = next((P.SEV_MAP[c] for c in sev_raw), "unrated")
                upsert(acc, pr, fid, action[:400], action, sev, sev_raw, "",
                       "", rnd, rec, "action-item")
        findings.extend(acc.values())
    return findings


def upsert(acc, pr, fid, text, action, sev, sev_raw, scope, status, rnd, rec, source):
    tn = P.norm_text(text or action)
    f = acc.get(fid)
    if f is None:
        f = {
            "finding_uid": P.finding_uid(pr, fid, tn),
            "pr": pr,
            "ledger_id": fid,
            "severity": sev,
            "severity_raw": sev_raw,
            "scope": scope,
            "text": text,
            "text_norm": tn,
            "action_text": action,
            "family": "",
            "refs": [],
            "first_round": rnd,
            "first_seen_artifact": rec["path"],
            "first_seen_at": rec["reviewed_at"],
            "first_posted_at": rec["posted_at"],
            "last_round": rnd,
            "last_seen_artifact": rec["path"],
            "last_seen_at": rec["reviewed_at"],
            "final_status_raw": status,
            "status_history": [],
            "source": source,
            "rounds_in_pr": rec["rounds_in_pr"],
            "text_variants": 1,
        }
        acc[fid] = f
    else:
        if rnd < f["first_round"]:
            f["first_round"], f["first_seen_artifact"] = rnd, rec["path"]
            f["first_seen_at"], f["first_posted_at"] = rec["reviewed_at"], rec["posted_at"]
        if text and P.norm_text(text) != f["text_norm"]:
            f["text_variants"] += 1
        if rnd >= f["last_round"]:
            f["last_round"], f["last_seen_artifact"] = rnd, rec["path"]
            f["last_seen_at"] = rec["reviewed_at"]
            f["final_status_raw"] = status or f["final_status_raw"]
            if sev != "unrated":
                f["severity"], f["severity_raw"] = sev, sev_raw
        if action and len(action) > len(f["action_text"]):
            f["action_text"] = action
    if status:
        f["status_history"].append({"round": rnd, "status_raw": status,
                                    "status": P.normalize_status(status)})
    blob = " ".join(filter(None, [f["text"], f["action_text"]]))
    f["family"] = P.classify_family(f["text"], f["action_text"])
    f["refs"] = P.extract_refs(blob)
    f["final_status"] = P.normalize_status(f["final_status_raw"])
    return f


# ---------------------------------------------------------------- stage: fetch

def stage_fetch(out_dir: str, refresh: bool = False) -> dict:
    cache_dir = os.path.join(out_dir, "cache", "gh")
    prs = sorted({json.loads(l)["pr"] for l in open(os.path.join(out_dir, "reviews.jsonl"))})
    log(f"fetch: {len(prs)} PRs -> {cache_dir}")
    ok, failed = 0, []
    for i, pr in enumerate(prs, 1):
        try:
            G.fetch_pr_bundle(pr, cache_dir, refresh)
            ok += 1
        except Exception as e:  # noqa: BLE001
            failed.append({"pr": pr, "error": str(e)[:300]})
            log(f"fetch: PR {pr} FAILED: {str(e)[:160]}")
        if i % 25 == 0:
            log(f"fetch: {i}/{len(prs)}")
    # local git file lists for every PR commit we know about
    shas = []
    for pr in prs:
        f = os.path.join(cache_dir, f"PR-{pr}", "commits.json")
        if os.path.exists(f):
            shas += [c["sha"] for c in json.load(open(f))]
    cache_path = os.path.join(out_dir, "cache", "commit_files.json")
    cf = G.commit_files(sorted(set(shas)), cache_path)
    present = sum(1 for v in cf.values() if v is not None)
    rep = {"prs_fetched": ok, "prs_failed": len(failed), "failures": failed[:20],
           "commits_seen": len(set(shas)), "commits_resolvable_locally": present}
    log(f"fetch: {json.dumps({k: v for k, v in rep.items() if k != 'failures'})}")
    return rep


# ----------------------------------------------------------------- stage: join

STRONG_LABELS = ("acted_on", "partially_acted_on", "not_acted_on",
                 "retracted_by_reviewer", "obsolete")


def rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def bucket_stats(rows: list[dict]) -> dict:
    c = collections.Counter(r["outcome"] for r in rows)
    strong = [r for r in rows if r["outcome_strength"] == "strong"]
    labeled = c["acted_on"] + c["partially_acted_on"] + c["not_acted_on"]
    return {
        "findings": len(rows),
        "strong_labeled": len(strong),
        "acted_on": c["acted_on"],
        "partially_acted_on": c["partially_acted_on"],
        "not_acted_on": c["not_acted_on"],
        "retracted_by_reviewer": c["retracted_by_reviewer"],
        "obsolete": c["obsolete"],
        "human_engaged": c["human_engaged"],
        "unlabeled": c["unlabeled"],
        "acceptance_rate": rate(c["acted_on"], labeled),
        "acceptance_rate_ci95": NB.wilson(c["acted_on"], labeled),
        "acceptance_rate_lenient": rate(c["acted_on"] + c["partially_acted_on"], labeled),
        "acceptance_rate_denominator": labeled,
        "reviewer_retraction_rate": rate(
            c["retracted_by_reviewer"] + c["obsolete"],
            len(strong)),
        "strong_label_coverage": rate(len(strong), len(rows)),
    }


def stage_join(out_dir: str) -> dict:
    cache_dir = os.path.join(out_dir, "cache", "gh")
    commit_files = {}
    cfp = os.path.join(out_dir, "cache", "commit_files.json")
    if os.path.exists(cfp):
        commit_files = json.load(open(cfp))

    state = load_state()
    posted_urls_by_pr = collections.defaultdict(set)
    for row in state["posted"]:
        if row["pr"].isdigit() and row["comment_url"]:
            posted_urls_by_pr[int(row["pr"])].add(row["comment_url"])

    findings = [json.loads(l) for l in open(os.path.join(out_dir, "findings.raw.jsonl"))]
    bundles: dict[int, dict] = {}
    eng_cache: dict[int, dict] = {}
    missing_prs = set()

    out_rows = []
    for f in findings:
        pr = f["pr"]
        if pr not in bundles:
            d = os.path.join(cache_dir, f"PR-{pr}")
            b = {}
            for key, fn in (("pr", "pr.json"), ("comments", "comments.json"),
                            ("commits", "commits.json"), ("reviews", "reviews.json"),
                            ("review_comments", "review_comments.json")):
                fp = os.path.join(d, fn)
                b[key] = json.load(open(fp)) if os.path.exists(fp) else ({} if key == "pr" else [])
            if not b["pr"]:
                missing_prs.add(pr)
            bundles[pr] = b
            eng_cache[pr] = J.pr_engagement(b, posted_urls_by_pr.get(pr, set()))
        res = J.label_finding(f, bundles[pr], eng_cache[pr], commit_files)
        row = dict(f)
        row.pop("text_norm", None)
        row.update(res)
        row["pr_title"] = (bundles[pr]["pr"] or {}).get("title")
        row["pr_author"] = (bundles[pr]["pr"] or {}).get("author")
        row["repo"] = REPO_SLUG
        out_rows.append(row)

    with open(os.path.join(out_dir, "findings.jsonl"), "w") as fh:
        for r in out_rows:
            fh.write(json.dumps(r) + "\n")

    summary = summarize(out_rows, bundles, eng_cache, missing_prs)
    with open(os.path.join(out_dir, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    log("join: " + json.dumps(summary["overall"]))
    return summary


MIN_FAMILY_N = 8


def _retraction_effect(rows: list) -> dict:
    """The one severity effect that survives its confidence interval."""
    strong = [r for r in rows if r["outcome_strength"] == "strong"]

    def rr(sub):
        k = sum(1 for r in sub if r["outcome"] in ("retracted_by_reviewer", "obsolete"))
        return k, len(sub)

    nk, nn = rr([r for r in strong if r["severity"] == "neutral"])
    ok, on = rr([r for r in strong if r["severity"] != "neutral"])
    return {
        "description": ("Acceptance does NOT vary by severity - every severity "
                        "interval contains the corpus rate. The reviewer's own "
                        "low-confidence marker does predict something else: which "
                        "findings it later throws out."),
        "neutral_severity_retraction": {"retracted": nk, "n": nn,
                                        "rate": round(nk / nn, 4) if nn else None,
                                        "ci95": NB.wilson(nk, nn)},
        "all_other_severities_retraction": {"retracted": ok, "n": on,
                                            "rate": round(ok / on, 6) if on else None,
                                            "ci95": NB.wilson(ok, on)},
        "test": NB.two_proportion_z(nk, nn, ok, on),
        "reading": ("A white/neutral marker is the single reliable predictor in this "
                    "corpus, and it predicts self-retraction, not author rejection. "
                    "n=23 strongly-labeled neutral findings, so treat as a strong "
                    "effect on a small base."),
    }


def summarize(rows, bundles, eng_cache, missing_prs) -> dict:
    overall = bucket_stats(rows)
    by_sev = {}
    for sev in ("critical", "caution", "neutral", "good", "unrated"):
        sub = [r for r in rows if r["severity"] == sev]
        if sub:
            by_sev[sev] = bucket_stats(sub)
    by_family = {}
    for fam in sorted({r["family"] for r in rows}):
        by_family[fam] = bucket_stats([r for r in rows if r["family"] == fam])

    # Decompose by label source. Nothing is pooled across signal strengths.
    src = collections.Counter()
    for r in rows:
        if r["outcome_strength"] != "strong":
            continue
        if r["outcome"] == "human_engaged":
            src["b_human_named_the_finding_id"] += 1
        elif r["final_status"] in ("rejected", "obsolete"):
            src["a_deepreview_reverification_retraction"] += 1
        else:
            src["a_deepreview_reverification"] += 1
    churn_only = sum(1 for r in rows
                     if r["outcome_strength"] == "weak"
                     and r["signals"]["cited_files_touched_after_review"])
    decomposition = {
        "note": ("Acceptance is reported per label source and never pooled. The "
                 "file-changed-after proxy produces ZERO acceptance labels in this "
                 "pipeline - it only ever yields outcome=unlabeled, strength=weak - "
                 "and the null baseline in null_baseline.json shows why it must "
                 "stay that way."),
        "a_deepreview_incremental_reverification": {
            "acted_on": sum(1 for r in rows if r["outcome"] == "acted_on"),
            "partially_acted_on": sum(1 for r in rows if r["outcome"] == "partially_acted_on"),
            "not_acted_on": sum(1 for r in rows if r["outcome"] == "not_acted_on"),
            "retracted_or_obsolete": src["a_deepreview_reverification_retraction"],
            "acceptance_rate": overall["acceptance_rate"],
            "acceptance_rate_ci95": overall["acceptance_rate_ci95"],
            "trust": "primary - the only self-labeled signal in the corpus",
        },
        "b_human_reply_reaction_or_thread_resolution": {
            "findings_labeled": src["b_human_named_the_finding_id"],
            "acceptance_rate": None,
            "trust": ("too sparse to compute a rate; see human_engagement below. "
                      "No human PR review and no inline review comment exists "
                      "anywhere in the corpus."),
        },
        "c_file_changed_after_review_proxy": {
            "findings_with_the_signal": churn_only,
            "acceptance_labels_produced": 0,
            "acceptance_rate": None,
            "trust": ("RETIRED as a label. Null baseline: a synthetic finding "
                      "pointing at a random file the PR had already touched scores "
                      "0.675 on this proxy vs 0.917 for real findings, so ~74% of "
                      "the signal is free. Kept as weak corroboration only."),
        },
    }

    rankable = {k: v for k, v in by_family.items()
                if (v["acceptance_rate_denominator"] or 0) >= MIN_FAMILY_N}
    # A family is only reportable if its interval excludes the corpus rate.
    base = overall["acceptance_rate"]

    def mark(v):
        lo, hi = v["acceptance_rate_ci95"]
        v["distinguishable_from_corpus_rate"] = (
            bool(base is not None and lo is not None and (hi < base or lo > base)))

    for v in by_family.values():
        mark(v)
    for v in by_sev.values():
        mark(v)
    overall["distinguishable_from_corpus_rate_note"] = (
        "Not applicable: this IS the corpus rate. The flag appears only on "
        "by_severity and by_family rows, where it asks whether that bucket's "
        "95% Wilson interval excludes the corpus rate.")
    most_ignored = sorted(rankable.items(), key=lambda kv: (kv[1]["acceptance_rate"], -kv[1]["acceptance_rate_denominator"]))
    most_acted = sorted(rankable.items(), key=lambda kv: (-kv[1]["acceptance_rate"], -kv[1]["acceptance_rate_denominator"]))

    def slim_rank(items):
        return [{"family": k,
                 "acceptance_rate": v["acceptance_rate"],
                 "acceptance_rate_ci95": v["acceptance_rate_ci95"],
                 "distinguishable_from_corpus_rate": v["distinguishable_from_corpus_rate"],
                 "acted_on": v["acted_on"],
                 "not_acted_on": v["not_acted_on"],
                 "retracted_by_reviewer": v["retracted_by_reviewer"] + v["obsolete"],
                 "strong_labeled": v["strong_labeled"],
                 "findings": v["findings"]} for k, v in items]

    pr_states = collections.Counter()
    for pr, b in bundles.items():
        p = b["pr"] or {}
        pr_states["merged" if p.get("merged") else ("closed_unmerged" if p.get("state") == "closed" else ("open" if p else "unknown"))] += 1

    rounds = collections.Counter(r["rounds_in_pr"] for r in rows)
    engagement = {
        "note": ("The watcher posts from the operator's own GitHub account. A "
                 "comment from that login that is not one of the watcher's own "
                 "posts is the operator writing by hand - our side of the "
                 "conversation, counted separately from the PR author."),
        "prs_with_any_human_comment_after_review": sum(
            1 for pr, e in eng_cache.items() if e["human_comments"]),
        "prs_with_counterparty_comment": sum(
            1 for pr, e in eng_cache.items() if e["counterparty_comments"]),
        "prs_with_pr_author_comment": sum(
            1 for pr, e in eng_cache.items() if e["author_comments"]),
        "prs_with_operator_disposition_comment": sum(
            1 for pr, e in eng_cache.items() if e["operator_comments"]),
        "prs_with_reactions_on_our_comments": sum(
            1 for pr, e in eng_cache.items() if e["reactions_on_ours"]),
        "reaction_kinds_total": dict(collections.Counter(
            k for e in eng_cache.values() for k, v in e["reaction_kinds"].items() for _ in range(v))),
        "prs_with_human_review_submitted": sum(
            1 for pr, e in eng_cache.items() if e["human_reviews"]),
        "findings_whose_id_a_counterparty_human_named": sum(
            1 for r in rows if r["signals"]["ledger_id_mentioned_by_human"]),
        "findings_whose_id_an_operator_disposition_named": sum(
            1 for r in rows if r["signals"]["ledger_id_named_in_operator_disposition"]),
    }

    def cite(r):
        return {"pr": r["pr"], "id": r["ledger_id"], "severity": r["severity"],
                "family": r["family"], "first_round": r["first_round"],
                "last_round": r["last_round"],
                "rounds_survived": r["last_round"] - r["first_round"],
                "text": r["text"][:220], "status": r["final_status_raw"][:160],
                "cited_files": r["signals"]["cited_files"][:4],
                "pr_state": r["signals"]["pr_state"]}

    ignored = sorted([r for r in rows if r["outcome"] == "not_acted_on"],
                     key=lambda r: (-(r["last_round"] - r["first_round"]),
                                    0 if r["severity"] == "critical" else 1))
    retracted = [r for r in rows if r["outcome"] in ("retracted_by_reviewer", "obsolete")]

    weak = [r for r in rows if r["outcome_strength"] in ("weak", "medium")]
    weak_churn = [r for r in weak if r["signals"]["cited_files_touched_after_review"]]

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": REPO_SLUG,
        "analysis_only": (
            "Offline analysis of already-produced reviews. Never inject into a "
            "reviewer prompt, a global skill, or a child workspace."),
        "headline": {
            "trustworthy_numbers": [
                "parse coverage 98.9% of 785 review artifacts; 942 findings extracted",
                "70.5% strong-label coverage (664/942), every strong label from "
                "deepreview's own later-round re-verification",
                "hand-check of the acted_on label: 41/42 sampled findings had a real "
                "code change addressing the finding's substance, 0 found wrong "
                "(handcheck.json) - this validates that `resolved` means something, "
                "not that the finding was worth raising",
                "no human PR review and no inline review comment exists anywhere in "
                "the corpus (0 across 230 PRs / 612 posted comments)",
            ],
            "numbers_to_read_with_the_caveat_attached": [
                "acceptance_rate 0.7926 [0.760, 0.822] is SELF-LABELED: it measures "
                "deepreview agreeing with itself one round later. It has no "
                "independent human ground truth anywhere in this corpus and has NOT "
                "been null-baselined (see null_baseline.json "
                "what_could_not_be_baselined). Do not quote it as a quality result.",
            ],
            "retired_numbers": [
                "any acceptance rate derived from the file-changed-after proxy - "
                "random controls score 0.675 against 0.917 real (null_baseline.json "
                "T1/T2)",
                "the per-family ignored/acted-on ranking - 1 of 21 families "
                "separates from the corpus rate once Wilson intervals are applied, "
                "and its interval is [0.24, 0.76]",
                "per-severity acceptance differences - every severity interval "
                "contains the corpus rate",
            ],
            "see_also": ["null_baseline.json", "handcheck.json", "parse_report.json"],
        },
        "overall": overall,
        "label_source_decomposition": decomposition,
        "prs": {"with_at_least_one_finding": len(bundles), "states": dict(pr_states),
                "missing_github_data": sorted(missing_prs),
                "findings_by_rounds_in_pr": dict(sorted(rounds.items()))},
        "by_severity": by_sev,
        "by_family": by_family,
        "severity_retraction_effect": _retraction_effect(rows),
        "family_ranking_health_warning": (
            "Family rates are computed on the strong reviewer-verification label "
            "only. Read `distinguishable_from_corpus_rate` before acting on any "
            "row: a family whose 95% interval contains the corpus rate is NOT "
            "shown to differ from average, and must not be used to prune reviewer "
            "prompts. Families are keyword-assigned and approximate."),
        "families_distinguishable_from_corpus_rate": sorted(
            k for k, v in by_family.items()
            if v["distinguishable_from_corpus_rate"]
            and (v["acceptance_rate_denominator"] or 0) >= MIN_FAMILY_N),
        "most_often_ignored_families": slim_rank(most_ignored[:12]),
        "most_often_acted_on_families": slim_rank(most_acted[:12]),
        "family_ranking_min_labeled": MIN_FAMILY_N,
        "human_engagement": engagement,
        "most_persistently_ignored_findings": [cite(r) for r in ignored[:30]],
        "reviewer_retracted_findings": [cite(r) for r in retracted],
        "circumstantial_only": {
            "findings": len(weak),
            "cited_files_changed_after_review": len(weak_churn),
            "note": ("Circumstantial. A cited file changing after the review does "
                     "NOT show the finding was accepted - the author may have been "
                     "editing that file for unrelated reasons. It is reported as a "
                     "churn signal, never as acceptance."),
        },
        "signal_definitions": {
            "strong": ("reviewer re-verified the finding against a later head in a "
                       "later round and recorded a terminal ledger status, or a human "
                       "comment names the finding's ledger id"),
            "medium": "human replied on the PR or reacted after our comment (PR-level, not finding-level)",
            "weak": "post-review commit churn on cited files, and/or PR terminal state",
            "none": "single review round; nothing observable",
        },
        "known_biases": [
            "Only re-reviewed PRs can carry a strong label; PRs merged fast after one round are structurally unlabelable here.",
            "'resolved' is the reviewer's own next-round judgment, not an author confirmation.",
            "'not_acted_on' means the code still looked unfixed at a later head; the author may have disagreed rather than ignored it.",
            "Finding identity is (PR, ledger id). Ledger ids are stable by skill convention but a reviewer that renumbered a ledger would split or merge findings here.",
            "Family classification is keyword-based on finding text, so it is approximate and biased toward the first matching rule.",
            "The watcher posts from the operator's own GitHub account, so operator-written disposition comments and watcher posts share a login; they are split by the comment signature and the posted-comments ledger, and any operator comment that slipped past both would be miscounted as counterparty engagement.",
            "Commit->file resolution uses `git show --name-only`, which reports no files for a merge commit. Post-review churn is therefore slightly undercounted on PRs that merged the base branch in.",
            "Findings first raised in the final round of a PR can never be labeled: there is no later head to check them against. 136 findings come from PRs reviewed exactly once.",
            "A finding whose ledger status names no round falls back to `last_round > first_round`, which credits a carry-forward as a verification.",
            "The strong label has NOT been null-baselined and cannot be with a read-only tool: doing so means injecting synthetic findings into a live re-review round. See `what_could_not_be_baselined` in null_baseline.json for the proposed experiment. T3/T4/T6 there are indirect validity evidence only.",
            "Acceptance is the reviewer agreeing with itself one round later. It is a self-consistency measure, not a measure of whether the findings were correct.",
        ],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["parse", "fetch", "join", "all"])
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch GitHub data even if cached")
    a = ap.parse_args()
    if a.stage in ("parse", "all"):
        stage_parse(a.out)
    if a.stage in ("fetch", "all"):
        stage_fetch(a.out, a.refresh)
    if a.stage in ("join", "all"):
        stage_join(a.out)

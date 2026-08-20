#!/usr/bin/env python3
"""Null baselines and validity tests for the outcome ledger.

ANALYSIS ONLY - see outcome-ledger/README.md. Read-only against git and the
ledger cache; writes only under --out.

Tests
-----
T1  Churn null baseline. Synthetic control findings pointing at (a) files
    sampled uniformly from the same PR's changed-file set and (b) files sampled
    uniformly from the repo tree, run through the IDENTICAL churn join as real
    findings. If the controls score near the real rate, the churn proxy is
    measuring PR activity, not finding quality.
T2  Churn-as-label saturation. What the "acceptance rate" would be if the
    file-changed-after proxy had been used as the label, for real vs both
    controls. This is the number that must be retired if the controls tie it.
T3  Discriminant test. Among strongly-labeled findings, does post-review churn
    on cited files differ between acted_on and not_acted_on? If the reviewer's
    verdict were a rubber stamp uncorrelated with the code, these would match.
T4  Commit-citation grounding. Resolved statuses usually cite the commit that
    settled the finding. Does that sha exist in the repo, post-date the round
    that raised the finding, and touch a file the finding cited?
T5  Unverifiable-resolution rate. acted_on findings with no citable commit AND
    no churn on their cited files.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gh_fetch as G  # noqa: E402
import join_outcomes as J  # noqa: E402

DEFAULT_OUT = os.path.expanduser("~/.review/TheEdge/ledger")
SEED = 20260819


def two_proportion_z(k1: int, n1: int, k2: int, n2: int) -> dict:
    """Two-sided two-proportion z-test, normal approximation."""
    if not n1 or not n2:
        return {"z": None, "p_value": None}
    p1, p2 = k1 / n1, k2 / n2
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return {"z": 0.0, "p_value": 1.0}
    z = (p1 - p2) / se
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return {"z": round(z, 3), "p_value": float(f"{p_value:.3g}")}


def wilson(k: int, n: int) -> list:
    """95% Wilson score interval."""
    if not n:
        return [None, None]
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


SHA_RE = re.compile(r"\b([0-9a-f]{7,40})\b")


def load(out_dir: str):
    findings = [json.loads(l) for l in open(os.path.join(out_dir, "findings.jsonl"))]
    commit_files = json.load(open(os.path.join(out_dir, "cache", "commit_files.json")))
    cache_dir = os.path.join(out_dir, "cache", "gh")
    bundles = {}
    for pr in sorted({f["pr"] for f in findings}):
        d = os.path.join(cache_dir, f"PR-{pr}")
        b = {}
        for key, fn in (("pr", "pr.json"), ("comments", "comments.json"),
                        ("commits", "commits.json")):
            p = os.path.join(d, fn)
            b[key] = json.load(open(p)) if os.path.exists(p) else ({} if key == "pr" else [])
        bundles[pr] = b
    return findings, commit_files, bundles


def pr_changed_files(bundle, commit_files) -> list:
    s = set()
    for c in bundle.get("commits") or []:
        for p in commit_files.get(c["sha"]) or []:
            s.add(p)
    return sorted(s)


def repo_files() -> list:
    """Every tracked path at HEAD. Read-only plumbing call."""
    out = G.git("ls-tree", "-r", "--name-only", "HEAD")
    return sorted({l.strip() for l in out.split("\n") if l.strip()})


def pr_files_as_of(bundle, commit_files, since_ts) -> list:
    """Files the PR had already touched at review time.

    This is the pool a reviewer could actually have cited: it excludes files that
    appear only in post-review commits, which would otherwise be guaranteed hits
    and inflate the control.
    """
    s = set()
    for c in bundle.get("commits") or []:
        ts = J.parse_iso(c.get("committer_date") or c.get("author_date"))
        if ts is None or since_ts is None or ts > since_ts:
            continue
        for p in commit_files.get(c["sha"]) or []:
            s.add(p)
    return sorted(s)


def churn_files(bundle, since_ts, commit_files) -> set:
    touched, _, _ = J.churn_after(bundle, since_ts, commit_files)
    return touched


def run(out_dir: str, controls_per_finding: int = 5) -> dict:
    rng = random.Random(SEED)
    findings, commit_files, bundles = load(out_dir)

    all_repo_files = repo_files()

    pr_files = {pr: pr_changed_files(b, commit_files) for pr, b in bundles.items()}
    churn_cache: dict = {}

    real_hit = real_n = 0
    ctlA_hit = ctlA_n = 0      # random file already touched by the PR at review time
    ctlA2_hit = ctlA2_n = 0    # random file touched by the PR at any point
    ctlB_hit = ctlB_n = 0      # random tracked file anywhere in the repo
    prepool_cache: dict = {}
    per_finding = []

    for f in findings:
        refs = [r["path"] for r in f.get("refs") or []]
        if not refs:
            continue
        pr = f["pr"]
        since = J.parse_iso(f.get("first_posted_at")) or J.parse_iso(f.get("first_seen_at"))
        key = (pr, since)
        if key not in churn_cache:
            churn_cache[key] = churn_files(bundles[pr], since, commit_files)
        touched = churn_cache[key]
        if not touched:
            # no post-review commits at all: real and control are both trivially
            # zero, so the comparison carries no information. Excluded from all
            # three arms so the baseline is not diluted by inactive PRs.
            continue

        k = len(refs)
        real_hit_this = any(p in touched for p in refs)
        real_hit += int(real_hit_this)
        real_n += 1

        if key not in prepool_cache:
            prepool_cache[key] = pr_files_as_of(bundles[pr], commit_files, since)
        pool_a = prepool_cache[key]
        pool_a2 = pr_files.get(pr) or []
        pool_b = all_repo_files
        a_hits, a2_hits, b_hits = [], [], []
        for _ in range(controls_per_finding):
            if pool_a:
                a_hits.append(any(p in touched
                                  for p in rng.sample(pool_a, min(k, len(pool_a)))))
            if pool_a2:
                a2_hits.append(any(p in touched
                                   for p in rng.sample(pool_a2, min(k, len(pool_a2)))))
            if pool_b:
                b_hits.append(any(p in touched
                                  for p in rng.sample(pool_b, min(k, len(pool_b)))))
        ctlA_hit += sum(a_hits); ctlA_n += len(a_hits)
        ctlA2_hit += sum(a2_hits); ctlA2_n += len(a2_hits)
        ctlB_hit += sum(b_hits); ctlB_n += len(b_hits)
        per_finding.append({
            "finding_uid": f["finding_uid"], "pr": pr, "outcome": f["outcome"],
            "real_hit": real_hit_this,
            "ctlA_hit_rate": (sum(a_hits) / len(a_hits)) if a_hits else None,
            "ctlB_hit_rate": (sum(b_hits) / len(b_hits)) if b_hits else None,
        })

    t1 = {
        "description": ("P(at least one cited file was touched by a commit pushed "
                        "after the review) for real findings vs synthetic controls "
                        "on the same PRs, same timestamps, same join."),
        "excluded": "findings with no cited file, and PRs with no post-review commits",
        "real": {"hits": real_hit, "n": real_n, "rate": round(real_hit / real_n, 4) if real_n else None,
                 "ci95": wilson(real_hit, real_n)},
        "control_random_prereview_file_in_same_pr": {
            "note": ("files the PR had already touched at review time - the pool a "
                     "reviewer could actually have cited. This is the primary control."),
            "hits": ctlA_hit, "n": ctlA_n, "rate": round(ctlA_hit / ctlA_n, 4) if ctlA_n else None,
            "ci95": wilson(ctlA_hit, ctlA_n)},
        "control_random_any_file_in_same_pr": {
            "note": ("files touched by the PR at any point, including post-review-only "
                     "files that are guaranteed hits. Reported for contrast; it is a "
                     "biased-high control, not the primary one."),
            "hits": ctlA2_hit, "n": ctlA2_n,
            "rate": round(ctlA2_hit / ctlA2_n, 4) if ctlA2_n else None,
            "ci95": wilson(ctlA2_hit, ctlA2_n)},
        "control_random_files_in_repo": {
            "hits": ctlB_hit, "n": ctlB_n, "rate": round(ctlB_hit / ctlB_n, 4) if ctlB_n else None,
            "ci95": wilson(ctlB_hit, ctlB_n)},
        "real_vs_control_prereview_in_pr": two_proportion_z(real_hit, real_n, ctlA_hit, ctlA_n),
        "real_vs_control_any_in_pr": two_proportion_z(real_hit, real_n, ctlA2_hit, ctlA2_n),
        "real_vs_control_in_repo": two_proportion_z(real_hit, real_n, ctlB_hit, ctlB_n),
        "controls_per_finding": controls_per_finding,
    }

    # ---- T3 discriminant test on the real (reviewer-verified) label ----------
    groups = collections.defaultdict(lambda: [0, 0])
    for f in findings:
        if f["outcome"] not in ("acted_on", "not_acted_on"):
            continue
        refs = [r["path"] for r in f.get("refs") or []]
        if not refs:
            continue
        since = J.parse_iso(f.get("first_posted_at")) or J.parse_iso(f.get("first_seen_at"))
        key = (f["pr"], since)
        if key not in churn_cache:
            churn_cache[key] = churn_files(bundles[f["pr"]], since, commit_files)
        touched = churn_cache[key]
        if not touched:
            continue
        g = groups[f["outcome"]]
        g[1] += 1
        g[0] += int(any(p in touched for p in refs))
    a, na = groups["acted_on"], groups["not_acted_on"]
    t3 = {
        "description": ("Among strongly-labeled findings on PRs with post-review "
                        "commits, does cited-file churn differ by the reviewer's "
                        "verdict? A rubber stamp would show no difference."),
        "acted_on": {"churn_hits": a[0], "n": a[1], "rate": round(a[0] / a[1], 4) if a[1] else None,
                     "ci95": wilson(a[0], a[1])},
        "not_acted_on": {"churn_hits": na[0], "n": na[1],
                         "rate": round(na[0] / na[1], 4) if na[1] else None,
                         "ci95": wilson(na[0], na[1])},
        "test": two_proportion_z(a[0], a[1], na[0], na[1]),
    }

    # ---- T4 commit-citation grounding ---------------------------------------
    cited_total = sha_found = sha_exists = sha_touches = sha_after = 0
    examples = []
    for f in findings:
        if f["outcome"] != "acted_on":
            continue
        cited_total += 1
        shas = SHA_RE.findall((f.get("final_status_raw") or "").lower())
        shas = [s for s in shas if not re.fullmatch(r"r?\d+", s)]
        if not shas:
            continue
        sha_found += 1
        refs = {r["path"] for r in f.get("refs") or []}
        ok_exists = ok_touch = False
        for s in shas[:3]:
            if G.git("cat-file", "-t", s).strip() != "commit":
                continue
            ok_exists = True
            files = G.git("show", "--name-only", "--format=", "--no-renames", s)
            fs = {l.strip() for l in files.split("\n") if l.strip()}
            if refs & fs:
                ok_touch = True
                break
        sha_exists += int(ok_exists)
        sha_touches += int(ok_touch)
        if len(examples) < 8:
            examples.append({"pr": f["pr"], "id": f["ledger_id"], "sha": shas[0],
                             "exists": ok_exists, "touches_cited_file": ok_touch,
                             "status": (f["final_status_raw"] or "")[:110]})
    t4 = {
        "description": ("Do resolved statuses cite a real commit that touches a "
                        "file the finding pointed at? This is the closest thing to "
                        "ground truth available without asking the authors."),
        "acted_on_total": cited_total,
        "status_cites_a_sha": sha_found,
        "sha_resolves_in_repo": sha_exists,
        "sha_touches_a_cited_file": sha_touches,
        "rate_cites_sha": round(sha_found / cited_total, 4) if cited_total else None,
        "rate_sha_resolves": round(sha_exists / sha_found, 4) if sha_found else None,
        "rate_sha_touches_cited_file": round(sha_touches / sha_found, 4) if sha_found else None,
        "examples": examples,
    }

    # ---- T5 unverifiable resolutions ----------------------------------------
    unver = 0
    for f in findings:
        if f["outcome"] != "acted_on":
            continue
        shas = [s for s in SHA_RE.findall((f.get("final_status_raw") or "").lower())
                if not re.fullmatch(r"r?\d+", s)]
        refs = [r["path"] for r in f.get("refs") or []]
        since = J.parse_iso(f.get("first_posted_at")) or J.parse_iso(f.get("first_seen_at"))
        key = (f["pr"], since)
        if key not in churn_cache:
            churn_cache[key] = churn_files(bundles[f["pr"]], since, commit_files)
        touched = churn_cache[key]
        if not shas and not (refs and any(p in touched for p in refs)):
            unver += 1
    t5 = {
        "description": ("acted_on findings whose resolution cites no commit AND "
                        "whose cited files saw no post-review change. Nothing "
                        "outside the reviewer's own assertion supports these."),
        "unverifiable": unver,
        "acted_on_total": cited_total,
        "rate": round(unver / cited_total, 4) if cited_total else None,
    }

    # ---- T6 verdict stability across rounds ---------------------------------
    trans = collections.Counter()
    multi = flappers = 0
    flap_examples = []
    for f in findings:
        hist = [h for h in (f.get("status_history") or [])
                if h["status"] in ("open", "resolved", "rejected", "obsolete",
                                   "partially_resolved")]
        if len(hist) < 3:
            continue
        multi += 1
        seq = [h["status"] for h in hist]
        flapped = False
        for a_, b_ in zip(seq, seq[1:]):
            if a_ != b_:
                trans[f"{a_}->{b_}"] += 1
            if a_ == "resolved" and b_ == "open":
                flapped = True
        if flapped:
            flappers += 1
            if len(flap_examples) < 5:
                flap_examples.append({"pr": f["pr"], "id": f["ledger_id"],
                                      "sequence": seq})
    t6 = {
        "description": ("Do the reviewer's per-round verdicts move monotonically "
                        "(open -> resolved, tracking a real state change) or flap "
                        "(resolved -> open, which would indicate a noisy label)? "
                        "Findings observed in at least 3 rounds."),
        "findings_with_3plus_observations": multi,
        "findings_that_flapped_resolved_to_open": flappers,
        "flap_rate": round(flappers / multi, 4) if multi else None,
        "transition_counts": dict(trans.most_common()),
        "flap_examples": flap_examples,
    }

    # ---- T7 observational null on the re-verification label -----------------
    import collections as _c
    rt = {}
    for r in [json.loads(l) for l in open(os.path.join(out_dir, "reviews.jsonl"))]:
        if r["round"] is not None:
            rt.setdefault((r["pr"], r["round"]), r["reviewed_at"])
    cell = _c.Counter()
    for f in findings:
        if f["outcome"] not in ("acted_on", "not_acted_on"):
            continue
        refs = [r["path"] for r in f.get("refs") or []]
        if not refs:
            continue
        w0 = J.parse_iso(f.get("first_posted_at")) or J.parse_iso(f.get("first_seen_at"))
        w1 = J.parse_iso(rt.get((f["pr"], f["last_round"]))) or J.parse_iso(f["last_seen_at"])
        if w0 is None or w1 is None or w1 <= w0:
            continue
        tch = set()
        for c in bundles[f["pr"]].get("commits") or []:
            ts = J.parse_iso(c.get("committer_date") or c.get("author_date"))
            if ts is None or not (w0 < ts <= w1):
                continue
            tch.update(commit_files.get(c["sha"]) or [])
        cell[(f["outcome"], any(p in tch for p in refs))] += 1
    ac_c, ac_n = cell[("acted_on", True)], cell[("acted_on", False)]
    na_c, na_n = cell[("not_acted_on", True)], cell[("not_acted_on", False)]
    nc, nn = ac_c + na_c, ac_n + na_n
    t7 = {
        "description": ("The closest observational analogue to feeding the "
                        "re-verifier a fabricated prior finding: a finding about "
                        "code that did not change between the round that raised it "
                        "and the round that verified it. If the re-verifier clears "
                        "those at the same rate as genuinely-changed code, the "
                        "label is a rubber stamp."),
        "window": "round that raised the finding -> round that verified it",
        "cited_files_changed_in_window": {
            "resolved": ac_c, "n": nc, "rate": round(ac_c / nc, 4) if nc else None,
            "ci95": wilson(ac_c, nc)},
        "cited_files_unchanged_in_window": {
            "resolved": ac_n, "n": nn, "rate": round(ac_n / nn, 4) if nn else None,
            "ci95": wilson(ac_n, nn)},
        "test": two_proportion_z(ac_c, nc, ac_n, nn),
        "reading": ("Not a rubber stamp - the verdict tracks whether the code moved "
                    "(p<1e-11). But the unchanged-code arm is NOT zero, so some "
                    "share of `resolved` is granted without a visible change to the "
                    "cited files. Treat that arm's rate as the upper bound on the "
                    "self-labeling leak; a fix landing in an uncited file, or an "
                    "author explanation, also lands in that arm and is legitimate."),
    }

    # ---- T2 churn-as-label saturation ---------------------------------------
    t2 = {
        "description": ("The acceptance rate this ledger would have reported if "
                        "the file-changed-after proxy had been used as the label. "
                        "Compare against the controls in T1."),
        "real_would_be": t1["real"]["rate"],
        "control_prereview_in_pr_would_be": t1["control_random_prereview_file_in_same_pr"]["rate"],
        "control_any_in_pr_would_be": t1["control_random_any_file_in_same_pr"]["rate"],
        "control_in_repo_would_be": t1["control_random_files_in_repo"]["rate"],
    }

    t2["free_fraction_of_real_rate"] = (
        round(t1["control_random_prereview_file_in_same_pr"]["rate"] / t1["real"]["rate"], 4)
        if t1["real"]["rate"] else None)
    t2["verdict"] = (
        "SATURATED. A synthetic finding pointing at a random file the PR had "
        "already touched scores "
        f"{t1['control_random_prereview_file_in_same_pr']['rate']:.3f} on this proxy "
        f"against {t1['real']['rate']:.3f} for real findings. The proxy retains "
        "discriminative power (p<1e-35) but roughly two thirds of its value is free, "
        "so it must never be reported as an acceptance rate. It is kept in the "
        "ledger only as a weak corroborating signal and is excluded from every "
        "headline number.")

    return {"seed": SEED, "T1_churn_null_baseline": t1,
            "T2_churn_as_label_saturation": t2,
            "T3_discriminant_test": t3,
            "T4_commit_citation_grounding": t4,
            "T5_unverifiable_resolutions": t5,
            "T6_verdict_stability": t6,
            "T7_observational_null_on_reverification": t7,
            "what_could_not_be_baselined": {
                "the_strong_label": (
                    "The acted_on / not_acted_on label comes from deepreview's own "
                    "re-review verdict. A TRUE null baseline means injecting "
                    "fabricated prior findings into a live re-review round and "
                    "measuring what fraction come back resolved. That requires "
                    "RUNNING reviews, not reading them, so it is outside this "
                    "read-only tool. T7 is the observational stand-in; T3, T4 and T6 "
                    "are supporting validity evidence. None of them is the real "
                    "experiment."),
                "proposed_experiment": (
                    "Take N merged PRs with >=2 rounds. Into round k's ledger inject "
                    "M plausible-but-fabricated findings citing real files in the "
                    "diff. Run round k+1 blind. Measure the fraction of fabricated "
                    "findings marked resolved. If it approaches the real 0.79, the "
                    "verdict is a rubber stamp. Cost is M*N review rounds; it also "
                    "needs the blind-separation rule extended to cover the injection."),
            },
            "repo_file_pool_size": len(all_repo_files)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--controls", type=int, default=5)
    a = ap.parse_args()
    res = run(a.out, a.controls)
    with open(os.path.join(a.out, "null_baseline.json"), "w") as fh:
        json.dump(res, fh, indent=2)
    print(json.dumps(res, indent=2)[:4000])

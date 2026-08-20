"""Read-only GitHub + git collectors for the outcome ledger.

ANALYSIS ONLY. Every call here is a GET. Nothing in this module posts, edits,
reacts, resolves, or otherwise mutates GitHub or the local repository.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

REPO_SLUG = "TheEdgeApp/TheEdge"
GIT_REPO = os.path.expanduser("~/TheEdge")

_ALLOWED_GIT = {"show", "log", "cat-file", "rev-parse", "merge-base", "ls-tree"}


def gh_api(path: str, paginate: bool = False, sleep: float = 0.15) -> object:
    cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
    if paginate:
        cmd += ["--paginate", "--slurp"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    time.sleep(sleep)
    if p.returncode != 0:
        raise RuntimeError(f"gh api {path} failed: {p.stderr.strip()[:400]}")
    data = json.loads(p.stdout or "null")
    if paginate and isinstance(data, list):
        flat = []
        for chunk in data:
            flat.extend(chunk if isinstance(chunk, list) else [chunk])
        return flat
    return data


def cached(cache_dir: str, name: str, fn, refresh: bool = False):
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, name)
    if os.path.exists(path) and not refresh:
        try:
            with open(path) as fh:
                return json.load(fh)
        except json.JSONDecodeError:
            pass
    data = fn()
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)
    return data


def slim_pr(d: dict) -> dict:
    return {
        "number": d.get("number"),
        "state": d.get("state"),
        "merged": bool(d.get("merged")),
        "merged_at": d.get("merged_at"),
        "closed_at": d.get("closed_at"),
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
        "merge_commit_sha": d.get("merge_commit_sha"),
        "head_sha": (d.get("head") or {}).get("sha"),
        "head_ref": (d.get("head") or {}).get("ref"),
        "base_ref": (d.get("base") or {}).get("ref"),
        "author": (d.get("user") or {}).get("login"),
        "title": d.get("title"),
        "draft": d.get("draft"),
        "additions": d.get("additions"),
        "deletions": d.get("deletions"),
        "changed_files": d.get("changed_files"),
    }


def slim_comments(items: list) -> list:
    out = []
    for c in items or []:
        r = c.get("reactions") or {}
        out.append({
            "id": c.get("id"),
            "user": (c.get("user") or {}).get("login"),
            "user_type": (c.get("user") or {}).get("type"),
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
            "html_url": c.get("html_url"),
            "body": c.get("body") or "",
            "reactions_total": r.get("total_count", 0),
            "reactions": {k: v for k, v in r.items()
                          if k not in ("url", "total_count") and v},
        })
    return out


def slim_commits(items: list) -> list:
    out = []
    for c in items or []:
        cm = c.get("commit") or {}
        out.append({
            "sha": c.get("sha"),
            "author_date": (cm.get("author") or {}).get("date"),
            "committer_date": (cm.get("committer") or {}).get("date"),
            "message": (cm.get("message") or "").split("\n")[0][:200],
            "author_login": (c.get("author") or {}).get("login"),
        })
    return out


def slim_reviews(items: list) -> list:
    return [{
        "id": r.get("id"),
        "user": (r.get("user") or {}).get("login"),
        "state": r.get("state"),
        "submitted_at": r.get("submitted_at"),
        "body_len": len(r.get("body") or ""),
        "body": (r.get("body") or "")[:2000],
    } for r in items or []]


def slim_review_comments(items: list) -> list:
    return [{
        "id": c.get("id"),
        "user": (c.get("user") or {}).get("login"),
        "created_at": c.get("created_at"),
        "path": c.get("path"),
        "line": c.get("line") or c.get("original_line"),
        "body": (c.get("body") or "")[:2000],
        "in_reply_to_id": c.get("in_reply_to_id"),
    } for c in items or []]


def fetch_pr_bundle(pr: int, cache_dir: str, refresh: bool = False) -> dict:
    d = os.path.join(cache_dir, f"PR-{pr}")
    pr_json = cached(d, "pr.json", lambda: slim_pr(gh_api(f"repos/{REPO_SLUG}/pulls/{pr}")), refresh)
    comments = cached(d, "comments.json",
                      lambda: slim_comments(gh_api(f"repos/{REPO_SLUG}/issues/{pr}/comments?per_page=100", True)), refresh)
    commits = cached(d, "commits.json",
                     lambda: slim_commits(gh_api(f"repos/{REPO_SLUG}/pulls/{pr}/commits?per_page=100", True)), refresh)
    reviews = cached(d, "reviews.json",
                     lambda: slim_reviews(gh_api(f"repos/{REPO_SLUG}/pulls/{pr}/reviews?per_page=100", True)), refresh)
    rcomments = cached(d, "review_comments.json",
                       lambda: slim_review_comments(gh_api(f"repos/{REPO_SLUG}/pulls/{pr}/comments?per_page=100", True)), refresh)
    return {"pr": pr_json, "comments": comments, "commits": commits,
            "reviews": reviews, "review_comments": rcomments}


# ------------------------------------------------------------------ local git

def git(*args: str) -> str:
    if not args or args[0] not in _ALLOWED_GIT:
        raise ValueError(f"read-only git only, got {args[:1]}")
    p = subprocess.run(["git", "-C", GIT_REPO, *args], capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


def commit_files(shas: list[str], cache_path: str) -> dict[str, list[str]]:
    """sha -> changed file paths, read-only, cached on disk."""
    cache: dict[str, list[str]] = {}
    if os.path.exists(cache_path):
        try:
            cache = json.load(open(cache_path))
        except json.JSONDecodeError:
            cache = {}
    missing = [s for s in shas if s and s not in cache]
    for i in range(0, len(missing), 40):
        batch = missing[i:i + 40]
        have = [s for s in batch if git("cat-file", "-t", s).strip() == "commit"]
        for s in batch:
            if s not in have:
                cache[s] = None  # object not present locally
        if not have:
            continue
        out = git("show", "--name-only", "--format=@@%H", "--no-renames", *have)
        cur = None
        for line in out.split("\n"):
            if line.startswith("@@"):
                cur = line[2:].strip()
                cache.setdefault(cur, [])
            elif cur is not None and line.strip():
                cache[cur].append(line.strip())
        for s in have:
            cache.setdefault(s, [])
    if missing:
        tmp = cache_path + ".tmp"
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(tmp, "w") as fh:
            json.dump(cache, fh)
        os.replace(tmp, cache_path)
    return cache

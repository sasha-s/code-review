#!/usr/bin/env python3
"""Mechanical PR description <-> head divergence detector.

Offline analysis + a shape that can run as a deterministic pre-pass inside a
review. Inputs are all already fetched by deepreview's Input step plus one
extra GraphQL field (`lastEditedAt`).

Never inject this file's *goldens* or adjudications into a reviewer prompt.
The detector output itself IS intended for the reviewer (it is derived only
from PR metadata the reviewer already has).
"""
import json, re, sys, os, math, collections
from datetime import datetime

SHA_RE = re.compile(r'\b([0-9a-f]{7,40})\b')
BACKTICK_SHA_RE = re.compile(r'`([0-9a-f]{7,40})`')
IDENT_RE = re.compile(r'\b([a-z]+(?:[A-Z][a-z0-9]+)+|[a-z_]{4,}_[a-z_]+|[A-Z][a-z]+[A-Z][A-Za-z]+)\b')
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'.-]{3,}")

# vocabulary that marks a commit as retracting/reversing an earlier ruling
REVERSAL_RE = re.compile(
    r'\b(revert(?:s|ed|ing)?|revers(?:e|es|ed|al|ing)|undo(?:es|ne)?|rescind\w*|retract\w*'
    r'|no longer|instead of|rather than|drop(?:s|ped|ping)? the|stop(?:s|ped)? '
    r'|remove(?:s|d)? the|replace(?:s|d)? the|abandon\w*|back out|backs out'
    r'|contradict\w*|opposite|wrong direction|fix(?:es|ed)? the .{0,24}direction'
    r'|correct(?:s|ed|ion)? the|was wrong|is wrong|not (?:a|the) )\b', re.I)

NORMATIVE_RE = re.compile(
    r'\b(is|are|qualifies|qualify|does not|do not|must|must not|shall|will|becomes?|remains?|cannot|can not)\b', re.I)

COUNT_WORDS = {'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,
               'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,
               'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,
               'nineteen':19,'twenty':20}
COMMIT_COUNT_RE = re.compile(r'\b(\d{1,2}|' + '|'.join(COUNT_WORDS) + r')\s+commits?\b', re.I)


def parse_ts(s):
    if not s: return None
    return datetime.strptime(s.replace('Z','+0000'), '%Y-%m-%dT%H:%M:%S%z')


def body_claims(body):
    """Normative claim sentences: bold spans and sentences with normative verbs."""
    claims = []
    for m in re.finditer(r'\*\*(.+?)\*\*', body, re.S):
        claims.append(m.group(1))
    for sent in re.split(r'(?<=[.;])\s+|\n', body):
        if NORMATIVE_RE.search(sent) and len(sent) > 25:
            claims.append(sent)
    return claims


def terms(text):
    out = set()
    for m in IDENT_RE.finditer(text):
        out.add(m.group(1).lower())
    for m in re.finditer(r'`([^`\n]{3,40})`', text):
        for w in WORD_RE.findall(m.group(1)):
            out.add(w.lower())
    for w in WORD_RE.findall(text):
        out.add(w.lower())
    return out


STOP = set('''this that with from have been will they their there where which what when
    into over under about after before more most some such than then them these those only
    also both each other same very much many need needs must should would could been being
    does doesn don't page pages line lines file files code test tests change changes commit
    commits review reviews base head main branch pull request issue docs doc note notes the
    and but not for are was were its it's you your our we us he she his her them are'''.split())


def detect(pr, commits, as_of_sha=None, df=None, corpus_n=1):
    """Return signal dict. `commits` newest-last, each {sha, committer_date, message}."""
    body = pr.get('body') or ''
    freeze = parse_ts(pr.get('lastEditedAt') or pr.get('createdAt'))
    if as_of_sha:
        idx = [i for i, c in enumerate(commits) if c['sha'].startswith(as_of_sha)]
        commits = commits[:idx[0] + 1] if idx else commits
    head = commits[-1]['sha'] if commits else None

    # Compare against AUTHORED date. A rebase rewrites every committer date to
    # the rebase timestamp; measured on this corpus, 34.3% of PRs carry rebased
    # or amended commits and 15.1% get a wrong post-body count from the
    # committer date (worst case: 64 reported against a true 39).
    authored_dates_available = bool(
        freeze and commits and all(c.get('author_date') for c in commits))
    post = ([c for c in commits if parse_ts(c['author_date']) > freeze]
            if authored_dates_available else [])

    # S1 structural: commits landed after the body was last touched
    s1 = len(post) if authored_dates_available else None

    # S2 stale pin: body cites a branch SHA that is not head
    sha_by_prefix = {}
    for c in commits:
        for L in range(7, 41):
            sha_by_prefix[c['sha'][:L]] = c['sha']
    cited = set(BACKTICK_SHA_RE.findall(body)) | set(SHA_RE.findall(body))
    order = {c['sha']: i for i, c in enumerate(commits)}
    resolved = {s: sha_by_prefix[s] for s in cited if s in sha_by_prefix}

    # SUPPRESSION 1 - the body anchors on head. Any older SHA it also cites is
    # history, not a stale pin. Structural: no dependence on phrasing.
    anchors_head = any(full == head for full in resolved.values())

    # SUPPRESSION 2 - a SHA cited on the same line as a strictly newer cited SHA
    # is a transition ("A -> B"), not a claim about what the PR describes.
    transition = set()
    for line in body.split('\n'):
        on_line = [s for s in resolved if s in line]
        if len(on_line) < 2: continue
        newest = max(order[resolved[s]] for s in on_line)
        for s in on_line:
            if order[resolved[s]] < newest: transition.add(s)

    pinned_behind = 0
    pinned_shas = []
    suppressed = []
    for s, full in resolved.items():
        if full == head: continue
        behind = len(commits) - 1 - order[full]
        if anchors_head or s in transition:
            suppressed.append((s, behind)); continue
        if behind > pinned_behind: pinned_behind = behind
        pinned_shas.append((s, behind))
    s2 = pinned_behind

    # S2b stated commit count vs actual
    s2b = None
    m = COMMIT_COUNT_RE.search(body)
    if m:
        tok = m.group(1).lower()
        stated = COUNT_WORDS.get(tok, None)
        if stated is None:
            try: stated = int(tok)
            except ValueError: stated = None
        if stated is not None and stated != len(commits):
            s2b = (stated, len(commits))

    # S3 reversal vocabulary in post-freeze commit messages
    rev_hits = []
    for c in post:
        mm = REVERSAL_RE.findall(c['message'])
        if mm:
            rev_hits.append((c['sha'][:9], sorted(set(x.strip().lower() for x in mm))[:4]))
    s3 = len(rev_hits)

    # S4 claim-term flip: a distinctive term from a normative body claim reappears
    #     in a post-freeze commit message that also carries reversal vocabulary.
    claim_terms = set()
    for cl in body_claims(body):
        for t in terms(cl):
            if t in STOP or len(t) < 4: continue
            if df is not None:
                # keep only terms that are distinctive across the PR-body corpus
                if df.get(t, 0) > max(2, corpus_n * 0.15): continue
            claim_terms.add(t)
    flips = []
    for c in post:
        if not REVERSAL_RE.search(c['message']): continue
        ct = terms(c['message'])
        shared = sorted(claim_terms & ct)
        if shared:
            flips.append((c['sha'][:9], shared[:6]))
    s4 = len(flips)

    # NOTE: every tier requires s1 > 0 (at least one commit landed after the
    # body was last edited). A stale-looking SHA citation in a body that has
    # been edited since the last commit is history, not a stale pin - firing on
    # s2 alone flags authors who documented their own reversal, which is the
    # remediation we want. (Observed: PR #1223 after the author fixed it.)
    tier = 0
    if s1 and (s2 > 0 or s2b): tier = 1
    if s1 and (s3 > 0 or s2 >= 2 or s2b): tier = 2
    if s1 and s4 > 0: tier = 3

    return dict(number=pr.get('number'), head=head, n_commits=len(commits),
                body_freeze=pr.get('lastEditedAt') or pr.get('createdAt'),
                authored_dates_available=authored_dates_available,
                s1_post_freeze_commits=s1, s2_pinned_behind=s2, s2_pinned=pinned_shas[:4],
                s2_anchors_head=anchors_head, s2_suppressed=suppressed[:4],
                s2b_commit_count=s2b, s3_reversal_commits=s3, s3_hits=rev_hits[:4],
                s4_claim_flips=s4, s4_hits=flips[:4], tier=tier)


def normalize_commits(raw):
    """Accept ledger-cache rows, `gh pr view --json commits`, or GraphQL nodes.

    Authored date is preferred and carried separately; committer date is only a
    fallback, because a rebase rewrites it on every commit.
    """
    out = []
    for c in raw:
        c = c.get('commit', c) if isinstance(c, dict) else c
        sha = c.get('sha') or c.get('oid')
        adate = (c.get('author_date') or c.get('authoredDate')
                 or (c.get('author') or {}).get('date'))
        date = (c.get('committer_date') or c.get('committedDate')
                or (c.get('committer') or {}).get('date'))
        msg = c.get('message')
        if msg is None:
            msg = '\n'.join(x for x in (c.get('messageHeadline'), c.get('messageBody')) if x)
        out.append(dict(sha=sha, committer_date=date, author_date=adate,
                        message=msg or ''))
    # GitHub returns PR commits in branch order; timestamps are not topological.
    return out


if __name__ == '__main__':
    # usage: desc_head_divergence.py PR.json [COMMITS.json]
    # PR.json may be `gh pr view <N> --json ...` output, a GraphQL pullRequest
    # node, or {pr:..., commits:...}. Signal A needs `lastEditedAt` or
    # `createdAt`; a null `lastEditedAt` falls back to `createdAt`.
    d = json.load(open(sys.argv[1]))
    while isinstance(d, dict) and 'pullRequest' not in d and 'data' in d: d = d['data']
    if isinstance(d, dict) and 'repository' in d: d = d['repository']
    if isinstance(d, dict) and 'pullRequest' in d: d = d['pullRequest']
    raw = (json.load(open(sys.argv[2])) if len(sys.argv) > 2
           else (d.get('commits', {}).get('nodes') if isinstance(d.get('commits'), dict)
                 else d.get('commits')))
    if not raw: sys.exit('no commits found; pass COMMITS.json or include commits in PR.json')
    if not (d.get('lastEditedAt') or d.get('createdAt')):
        print('WARNING: no lastEditedAt or createdAt in input - Signal A '
              'cannot evaluate provenance.',
              file=sys.stderr)
    commits = normalize_commits(raw)
    if any(not c.get('author_date') for c in commits):
        print('WARNING: authoredDate is unavailable for one or more commits - '
              'Signal A will not report a post-body commit count.',
              file=sys.stderr)
    print(json.dumps(detect(d, commits), indent=1))

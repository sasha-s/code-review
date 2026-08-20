"""Parse deepreview markdown artifacts into structured findings.

ANALYSIS ONLY. This module reads review artifacts after the fact. It must never
be loaded into a reviewer prompt, a global skill, or a child workspace. See
outcome-ledger/README.md.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass, field, asdict

SEV_MAP = {"🔴": "critical", "🟡": "caution", "🟢": "good", "⚪": "neutral"}

# Ordered: first match wins. Patterns are regexes matched against normalized
# finding text. Word boundaries matter here: a bare "lock" substring also
# matches "blocking", which is how an earlier pass mislabelled a third of the
# corpus as concurrency findings.
FAMILY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("pr-hygiene", (r"\bpr body\b", r"\btest count\b", r"\bcommit message\b",
                   r"\bpr description\b", r"\bchangelog\b", r"\btitle claims\b")),
    ("build-ci-tooling", (r"\bprettier\b", r"\beslint\b", r"\blint(ing|er)?\b",
                         r"\bformat:check\b", r"\btypecheck\b", r"\btsc\b",
                         r"\bci (job|run|pipeline|fails)\b", r"\bbuild fails\b",
                         r"\blockfile\b", r"\btoolchain\b", r"\bcompil(e|ation) error")),
    ("auth-authz", (r"\bauthoriz", r"\bauthentic", r"\bpermission", r"\baccess control\b",
                    r"\bunauthenticated\b", r"\bprivilege", r"\brbac\b", r"\bacl\b",
                    r"\badmin-only\b", r"\bimpersonat", r"\bsigner\b", r"\bsignature verif",
                    r"\bowner check\b", r"\btenant\b")),
    ("replay-idempotency", (r"\breplay", r"\bidempot", r"\bdouble-(spend|apply|undo|count|debit|credit)",
                            r"\bduplicate (submission|dispatch|row|write)", r"\breprocess",
                            r"\bexactly-once\b", r"\bat-least-once\b", r"\bdedup",
                            r"\bnonce\b", r"\bretr(y|ies|ied) .*(same|again|twice)")),
    ("concurrency-race", (r"\brace\b", r"\brace condition\b", r"\bconcurrent", r"\bconcurrency\b",
                          r"(?<!b)\block(s|ed|ing)?\b(?! (diagram|quote))", r"\bmutex\b",
                          r"\binterleav", r"\btoctou\b", r"\bserializab",
                          r"\btransaction boundar", r"\bsimultaneous", r"\bin parallel\b")),
    ("partial-write-rollback", (r"\brollback\b", r"\bpartial (success|write|failure|apply)",
                                r"\bhalf-(applied|written)", r"\bstranded?\b", r"\bcompensat",
                                r"\bnon-terminal state\b", r"\borphan", r"\bstuck (pending|in)",
                                r"\bleaves? .* (inconsistent|pending|unrecorded|unset)")),
    ("error-handling", (r"\btry/catch\b", r"\bcatch (block|arm|clause)\b", r"\bswallow",
                        r"\bsilently (ignore|drop|fail)", r"\bunhandled\b",
                        r"\berror (handling|path|boundary)\b", r"\bexception\b",
                        r"\bfails? open\b", r"\bfail-open\b", r"\bthrows? .*(uncaught|unhandled)")),
    ("input-validation", (r"\bvalidat", r"\bsanitiz", r"\buntrusted input\b", r"\binjection\b",
                          r"\bescape\b", r"\buser-supplied\b", r"\bunchecked input\b",
                          r"\bzod\b", r"\bvalidator\b", r"\bschema (is )?not .*pinned")),
    ("money-precision", (r"\brounding\b", r"\bprecision\b", r"\bdecimals?\b", r"\bfloat\b",
                         r"\boverflow", r"\bunderflow", r"\blamport", r"\bbasis point",
                         r"\bfee (calculation|math|cap|rate)\b", r"\bbalance drift\b",
                         r"\bescrow\b", r"\bpayout\b")),
    ("null-undefined", (r"\bnull\b", r"\bundefined\b", r"\bnullish\b", r"\boptional chain",
                        r"\bmissing field\b", r"\babsent vs\b", r"\bempty vs\b",
                        r"\bnon-null assertion\b")),
    ("api-contract", (r"\bapi contract\b", r"\bendpoint (returns|accepts)\b", r"\bopenapi\b",
                      r"\bbreaking change\b", r"\bbackward(s)? compat", r"\bresponse shape\b",
                      r"\bpayload shape\b", r"\brequest shape\b", r"\bpublic (api|surface)\b",
                      r"\bsignature change\b", r"\breturn type\b", r"\bwire format\b",
                      r"\bcontract\b(?! address)")),
    ("data-consistency", (r"\bdrift\b", r"\bout of sync\b", r"\bmismatch", r"\binvariant\b",
                          r"\bconsistency\b", r"\bstale (read|data|snapshot|row)\b",
                          r"\bdiverge", r"\breconcil", r"\bsource of truth\b",
                          r"\bdisagree", r"\bdouble-?count")),
    ("migration-schema", (r"\bmigration\b", r"\bbackfill\b", r"\bschema change\b",
                          r"\bindex on\b", r"\bnew column\b", r"\bdb schema\b",
                          r"\bdeploy order\b", r"\bexisting rows\b")),
    ("resource-bounds", (r"\bunbounded\b", r"\bpaginat", r"\bpage size\b", r"\bmemory\b",
                         r"\bleak\b", r"\btimeout\b", r"\brate limit", r"\bbudget\b",
                         r"\bquota\b", r"\bn\+1\b", r"\bhot loop\b", r"\bthrottl",
                         r"\bread cap\b", r"\brow (cap|limit)\b", r"\bscans? \d")),
    ("performance", (r"\bperformance\b", r"\blatency\b", r"\bo\(n\^?2\)", r"\bquadratic\b",
                     r"\bexpensive\b", r"\bhot path\b", r"\bslow(er|down)?\b", r"\bcost\b")),
    ("observability", (r"\blogs?\b", r"\blogging\b", r"\bmetrics?\b", r"\balert",
                       r"\btelemetry\b", r"\btrace\b", r"\bmonitor", r"\bdashboard\b",
                       r"\bsilent failure\b", r"\bno visibility\b", r"\bobservab",
                       r"\banalytics\b", r"\boperator\b", r"\boncall\b")),
    ("config-flags", (r"\bfeature flag\b", r"\benv(ironment)? var", r"\bconfig(uration)?\b",
                      r"\bhard-?coded\b", r"\bmagic number\b", r"\bconstant\b",
                      r"\bpinned?\b", r"\bdefault value\b")),
    ("lifecycle-state-machine", (r"\bstate machine\b", r"\blifecycle\b", r"\bterminal state\b",
                                 r"\bstatus transition", r"\btransition(s|ed)? (to|from|into)\b",
                                 r"\bsettle(d|ment)?\b", r"\bcancel(led|lation)?\b",
                                 r"\bexpir(y|ed|ation)\b", r"\bpending\b")),
    ("scheduling-jobs", (r"\bcron\b", r"\bschedul", r"\bwatchdog\b", r"\bjob\b",
                         r"\bbackground (task|run)\b", r"\bcadence\b", r"\bsweep\b",
                         r"\bpoll(s|ing|ed)?\b", r"\bworker\b")),
    ("caching-staleness", (r"\bcache", r"\bcached\b", r"\bstale\b", r"\binvalidat",
                           r"\bttl\b", r"\bmemoi", r"\brefresh(es|ed)?\b")),
    ("test-coverage", (r"\btests?\b", r"\bcoverage\b", r"\bassert", r"\bfixture\b",
                       r"\bmock", r"\bregression test\b", r"\buntested\b")),
    ("docs-drift", (r"\bdocs?\b", r"\bdocument", r"\breadme\b", r"\bcomment says\b",
                    r"\bstale comment\b", r"\bjsdoc\b", r"\bdesign doc\b", r"\bspec\b")),
    ("frontend-ui", (r"\brender", r"\breact\b", r"\bcomponent\b", r"\bcss\b",
                     r"\buse(state|effect|memo|callback)\b", r"\bui\b", r"\bbrowser\b",
                     r"\bclient-side\b")),
    ("dead-code-cleanup", (r"\bdead code\b", r"\bunused\b", r"\bunreachable\b",
                           r"\bleftover\b", r"\bno longer used\b", r"\bduplicated? (helper|code)\b")),
    ("naming-style", (r"\bnaming\b", r"\brenam", r"\btypo\b", r"\breadability\b", r"\bstyle\b")),
]

_FAMILY_RE = [(fam, [re.compile(p) for p in pats]) for fam, pats in FAMILY_RULES]


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"`+", "", s)
    s = re.sub(r"[*_]{1,3}", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[^\w\s./:#-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def classify_family(title: str, detail: str = "") -> str:
    """Classify on the one-line finding claim first; fall back to the longer
    recommendation prose only when the claim is too short to key on."""
    primary = norm_text(title)
    for family, pats in _FAMILY_RE:
        for p in pats:
            if p.search(primary):
                return family
    if detail:
        secondary = norm_text(detail)[:600]
        for family, pats in _FAMILY_RE:
            for p in pats:
                if p.search(secondary):
                    return family
    return "other"


FILE_REF_RE = re.compile(
    r"`([A-Za-z0-9_./+-]*[A-Za-z0-9_-]+\.[A-Za-z0-9]{1,6})(?::(\d+)(?:-(\d+))?)?`"
)
BARE_REF_RE = re.compile(
    r"(?<![\w`/])((?:[A-Za-z0-9_.+-]+/)+[A-Za-z0-9_.+-]+\.[A-Za-z0-9]{1,6})(?::(\d+))?"
)


def extract_refs(text: str) -> list[dict]:
    refs: dict[str, dict] = {}
    for m in list(FILE_REF_RE.finditer(text)) + list(BARE_REF_RE.finditer(text)):
        path = m.group(1)
        if path.startswith("."):
            continue
        if "/" not in path and path.count(".") < 1:
            continue
        line = m.group(2)
        cur = refs.setdefault(path, {"path": path, "lines": []})
        if line:
            v = int(line)
            if v not in cur["lines"]:
                cur["lines"].append(v)
    return sorted(refs.values(), key=lambda r: r["path"])


# ---------------------------------------------------------------- status vocab

STATUS_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("rejected", ("rejected", "not a bug", "not an issue", "not a defect",
                  "invalid", "wontfix", "won't fix", "withdrawn", "retracted",
                  "low-value", "non-issue", "dropped")),
    ("obsolete", ("obsolete", "moot", "no longer applies", "superseded")),
    ("resolved", ("resolved", "fixed", "done", "addressed", "merged", "closed")),
    ("open", ("still-open", "still open", "still", "open", "reopened",
              "unchanged", "new", "pending", "outstanding", "partially",
              "accepted/tracked", "deferred", "tracked")),
]


def normalize_status(raw: str) -> str:
    # Split on the parenthetical BEFORE normalizing: norm_text drops brackets, so
    # normalizing first would let a word from the evidence clause ("superseded",
    # "rejected an earlier...") outrank the verdict word itself.
    head = norm_text(re.split(r"[(\[]", raw or "", 1)[0])
    t = norm_text(raw)
    if not t or t in {"-", "--"}:
        return "unknown"
    if not head:
        head = t
    if "resolv" in head and "obsolet" in head:
        return "resolved"
    if head.startswith("partially") or head.startswith("partly"):
        return "partially_resolved"
    for label, keys in STATUS_RULES:
        for k in keys:
            if head.startswith(k) or (" " + k) in (" " + head):
                return label
    return "unknown"


ROUND_CITE_RE = re.compile(r"\br(\d+)\b")


def status_cited_round(raw: str) -> int | None:
    m = ROUND_CITE_RE.search(norm_text(raw))
    return int(m.group(1)) if m else None


# ------------------------------------------------------------------- artifacts

COMMENT_NAME_RE = re.compile(r"comment", re.I)
FULL_SHA_RE = re.compile(r"\b([0-9a-f]{40})\b")
ROUND_RE = re.compile(r"\*{0,2}Review round:?\*{0,2}\s*[:\-]?\s*(\d+)", re.I)
ROUND_RE2 = re.compile(r"^\s*[-*]?\s*Review round:\s*(\d+)", re.I | re.M)
PR_DIR_RE = re.compile(r"^PR-(\d+)$")


@dataclass
class Finding:
    finding_uid: str
    pr: int
    ledger_id: str
    severity: str
    severity_raw: str
    scope: str
    text: str
    text_norm: str
    family: str
    refs: list = field(default_factory=list)
    first_round: int = 0
    first_seen_artifact: str = ""
    first_seen_at: str = ""
    last_round: int = 0
    last_seen_artifact: str = ""
    last_seen_at: str = ""
    final_status_raw: str = ""
    final_status: str = "unknown"
    status_history: list = field(default_factory=list)
    source: str = "ledger"
    action_text: str = ""


def find_review_files(reviews_root: str) -> list[tuple[int, str]]:
    out = []
    for d in sorted(os.listdir(reviews_root)):
        m = PR_DIR_RE.match(d)
        if not m:
            continue
        pr = int(m.group(1))
        p = os.path.join(reviews_root, d)
        if not os.path.isdir(p):
            continue
        for fn in sorted(os.listdir(p)):
            if not fn.endswith(".md"):
                continue
            if COMMENT_NAME_RE.search(fn):
                continue
            out.append((pr, os.path.join(p, fn)))
    return out


def split_table(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_sep_row(cells: list[str]) -> bool:
    return all(set(c) <= set("-: ") and c for c in cells)


def parse_ledger(text: str) -> list[dict]:
    """Return ledger rows from every `| ID | ... |` table in the document."""
    rows: list[dict] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.lstrip().startswith("|"):
            hdr = split_table(ln)
            hl = [h.lower() for h in hdr]
            if hl and hl[0] in {"id", "#", "finding id"} and len(hdr) >= 3:
                idx = {}
                for j, h in enumerate(hl):
                    if h.startswith("sev"):
                        idx["sev"] = j
                    elif h.startswith("scope"):
                        idx["scope"] = j
                    elif h.startswith("finding") or h.startswith("issue") or h.startswith("summary") or h.startswith("title"):
                        idx["finding"] = j
                    elif h.startswith("status") or h.startswith("state") or h.startswith("disposition"):
                        idx["status"] = j
                if "finding" in idx and "status" in idx:
                    i += 1
                    while i < len(lines) and lines[i].lstrip().startswith("|"):
                        cells = split_table(lines[i])
                        i += 1
                        if is_sep_row(cells) or len(cells) < len(hdr) - 1:
                            continue
                        rid = cells[0].strip().strip("*` ")
                        if not re.match(r"^[A-Za-z]{1,3}\d+$", rid):
                            continue
                        rows.append({
                            "id": rid.upper(),
                            "sev": cells[idx["sev"]] if idx.get("sev", -1) < len(cells) and "sev" in idx else "",
                            "scope": cells[idx["scope"]] if "scope" in idx and idx["scope"] < len(cells) else "",
                            "finding": cells[idx["finding"]] if idx["finding"] < len(cells) else "",
                            "status": cells[idx["status"]] if idx["status"] < len(cells) else "",
                        })
                    continue
        i += 1
    return rows


ACTION_HDR_RE = re.compile(r"^#{2,4}\s*(Recommendations?|Questions?(?:\s+[Ff]or\s+the\s+[Aa]uthor)?)\s*$", re.M | re.I)
ACTION_ITEM_RE = re.compile(
    r"^\s*(?:\d+[.)]|[-*])\s*\**\s*\[?([A-Za-z]{1,3}\d+)\]?\**\s*[:\-–—]?\s*(.*)$"
)


def parse_action_items(text: str) -> dict[str, str]:
    """Map ledger id -> Recommendation/Question prose (which carries file:line)."""
    out: dict[str, str] = {}
    for m in ACTION_HDR_RE.finditer(text):
        start = m.end()
        nxt = re.search(r"^#{1,4}\s+\S", text[start:], re.M)
        block = text[start:start + (nxt.start() if nxt else len(text) - start)]
        cur_id = None
        buf: list[str] = []
        for line in block.split("\n"):
            im = ACTION_ITEM_RE.match(line)
            if im and re.match(r"^[A-Za-z]{1,3}\d+$", im.group(1)):
                if cur_id:
                    out.setdefault(cur_id, " ".join(buf).strip())
                cur_id = im.group(1).upper()
                buf = [im.group(2)]
            elif cur_id and line.strip():
                buf.append(line.strip())
            elif cur_id and not line.strip():
                out.setdefault(cur_id, " ".join(buf).strip())
                cur_id, buf = None, []
        if cur_id:
            out.setdefault(cur_id, " ".join(buf).strip())
    return {k: v for k, v in out.items() if v}


def parse_review_file(pr: int, path: str) -> dict:
    text = open(path, encoding="utf-8", errors="replace").read()
    head = None
    m = re.search(r"Full head SHA:?\**\s*`?([0-9a-f]{40})`?", text)
    if m:
        head = m.group(1)
    if not head:
        m = re.search(r"(?:Prepared head|Head)\**\s*[:\-].{0,80}?`?([0-9a-f]{40})`?", text[:2000])
        if m:
            head = m.group(1)
    if not head:
        m = re.search(r"([0-9a-f]{7,40})", os.path.basename(path))
        if m:
            head = m.group(1)
    rm = ROUND_RE.search(text[:4000]) or ROUND_RE2.search(text[:4000])
    rnd = int(rm.group(1)) if rm else None
    return {
        "pr": pr,
        "path": path,
        "head": head,
        "round": rnd,
        "mtime": os.path.getmtime(path),
        "ledger_rows": parse_ledger(text),
        "action_items": parse_action_items(text),
        "heading_findings": [],
        "has_ledger_table": bool(re.search(r"^\|\s*ID\s*\|", text, re.M | re.I)),
        "bytes": len(text),
    }


def finding_uid(pr: int, ledger_id: str, text_norm: str) -> str:
    h = hashlib.sha1(f"TheEdge|{pr}|{ledger_id}|{text_norm[:160]}".encode()).hexdigest()
    return h[:16]


# ------------------------------------------ fallback: `## Findings` H3 headings

SEV_WORD_RE = re.compile(
    r"^\[?(critical|caution|high|medium|low|major|minor|blocker|info|nit)\]?$", re.I)
SEV_WORD_MAP = {
    "critical": "critical", "blocker": "critical", "major": "critical", "high": "critical",
    "caution": "caution", "medium": "caution", "minor": "caution",
    "low": "neutral", "info": "neutral", "nit": "neutral",
}
FINDINGS_SECTION_RE = re.compile(
    r"^#{2}\s*(?:Findings?|Open Findings?|Non-?Blocking Notes?|Recommendations?|"
    r"Open Questions?|Questions?)\b.*$", re.M | re.I)


def parse_findings_headings(text: str) -> list[dict]:
    """Extract `### <ID> - <Sev> - <title>` / `### [Sev] <title>` findings.

    Used only for artifacts that carry no `| ID | Sev | ... |` ledger table.
    """
    out: list[dict] = []
    for m in FINDINGS_SECTION_RE.finditer(text):
        start = m.end()
        nxt = re.search(r"^#{1,2}\s+\S", text[start:], re.M)
        block = text[start:start + (nxt.start() if nxt else len(text) - start)]
        for hm in re.finditer(r"^#{3,4}\s+(.+?)\s*$", block, re.M):
            title = hm.group(1).strip()
            body_start = hm.end()
            bn = re.search(r"^#{1,4}\s+\S", block[body_start:], re.M)
            body = block[body_start:body_start + (bn.start() if bn else len(block) - body_start)]
            fid, sev, rest = None, "unrated", title
            parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", title)]
            if parts and re.match(r"^\[?([A-Za-z]{1,3}\d+)\]?$", parts[0].strip("*`[] ")):
                fid = re.sub(r"[^A-Za-z0-9]", "", parts[0]).upper()
                parts = parts[1:]
            if parts and SEV_WORD_RE.match(parts[0].strip("*`[] ")):
                sev = SEV_WORD_MAP[parts[0].strip("*`[] ").lower()]
                parts = parts[1:]
            lead = re.match(r"^\[(critical|caution|high|medium|low|major|minor|blocker|info|nit)\]\s*(.+)$",
                            " - ".join(parts) if parts else title, re.I)
            if lead:
                sev = SEV_WORD_MAP[lead.group(1).lower()]
                parts = [lead.group(2)]
            rest = " - ".join(parts).strip() if parts else title
            for c in title:
                if c in SEV_MAP:
                    sev = SEV_MAP[c]
            if not rest or len(rest) < 12:
                continue
            out.append({"id": fid, "sev": sev, "title": rest, "body": body.strip()[:1500]})
    return out


NUM_ITEM_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")


def parse_unnumbered_action_items(text: str) -> list[dict]:
    """Numbered Questions/Recommendations that carry no ledger ID.

    Only used for artifacts with no ledger table; ids are synthesised as
    `QA<n>` / `RA<n>` so they never collide with real `Q<n>` / `R<n>` ids.
    """
    out: list[dict] = []
    for m in ACTION_HDR_RE.finditer(text):
        kind = "QA" if m.group(1).lower().startswith("question") else "RA"
        start = m.end()
        nxt = re.search(r"^#{1,4}\s+\S", text[start:], re.M)
        block = text[start:start + (nxt.start() if nxt else len(text) - start)]
        cur, buf = None, []
        for line in block.split("\n"):
            im = NUM_ITEM_RE.match(line)
            if im:
                if cur:
                    out.append({"id": f"{kind}{cur}", "text": " ".join(buf).strip()})
                cur, buf = im.group(1), [im.group(2)]
            elif cur and line.strip():
                buf.append(line.strip())
        if cur:
            out.append({"id": f"{kind}{cur}", "text": " ".join(buf).strip()})
    seen, uniq = set(), []
    for it in out:
        if it["id"] in seen or len(it["text"]) < 15:
            continue
        seen.add(it["id"])
        uniq.append(it)
    return uniq

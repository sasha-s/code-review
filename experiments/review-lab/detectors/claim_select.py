"""Rule 7 claim selector, v2: assertion-shaped, NOT formatting-keyed.

v1 keyed on bold spans + normative markers. Measured on 166 bodies it looked
cheap (median 2) but that measured the SELECTOR, not coverage: on a claim-dense
body it took 2 of ~8 verifiable claims because the author does not use bold.
"""
import re

IDENT = re.compile(r'`[^`\n]{2,60}`|\b[a-z]+[A-Z][A-Za-z0-9]*\b|\b[a-z]{3,}_[a-z_]{2,}\b|\[[a-zA-Z, ]{6,}\]')
QUANT  = re.compile(r'\b\d[\d,_.]*\s*(\*|x|×)?\s*(\(?N\s*\+\s*1\)?)?\b')
# predicates that assert a property of the shipped change
ASSERT = re.compile(
    r'\b(is|are|was|were|has|have|does|do|will|can|cannot|never|always|only|'
    r'preserv\w+|copies|copied|drop\w+|keep\w+|stay\w+|index(es|ed)?|deriv\w+|'
    r'deliver\w+|deriv\w+|bound(ed)?|deriv\w+|writ(es|ten)|patch\w*|deriv\w+|'
    r'implement\w*|deriv\w+|guarantee\w*|ensur\w*|enforc\w*|reject\w*|accept\w*|'
    r'must|shall|required|normative|invariant|disagree\w*|differ\w*|unique|'
    r'exclud\w*|includ\w*|fail\w*|pass\w*|remain\w*|becomes?|returns?|emits?)\b',
    re.I)
# Step 0g owns these; excluding them keeps the two checks from duplicating
PROVENANCE = re.compile(r'`[0-9a-f]{7,40}`|\b\d{1,2} commits?\b|'
    r'\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen) commits?\b|'
    r'\btrailers\b|check-runs?\b|completed/success', re.I)
NOISE = re.compile(r'^\s*(#{1,6}\s|\||-{3,}|```)|^\s*$|\?\s*$')

def units(body):
    """Sentences AND list items - bullets are the dominant claim form."""
    body = re.sub(r'```.*?```', '', body, flags=re.S)
    out = []
    for line in body.split('\n'):
        if NOISE.match(line): continue
        line = re.sub(r'^\s*(?:[-*+]|\d+\.)\s+', '', line).strip()
        if not line: continue
        # split long lines into sentences, but keep short bullets whole
        parts = re.split(r'(?<=[.;])\s+(?=[A-Z`])', line) if len(line) > 200 else [line]
        out.extend(p.strip() for p in parts if p.strip())
    return out

def select(body, cap=20):
    claims = []
    for u in units(body):
        if len(u.split()) < 2: continue
        # Step 0g owns provenance fragments, not the rest of the sentence. A
        # body often pins a SHA and states a substantive contract in one line.
        substantive = PROVENANCE.sub('', u)
        if not ASSERT.search(substantive): continue
        if not (IDENT.search(substantive) or QUANT.search(substantive)): continue
        claims.append(re.sub(r'\s+', ' ', u))
    # dedupe by normalised prefix
    seen, out = set(), []
    for c in claims:
        k = re.sub(r'[^a-z0-9]', '', c.lower())[:60]
        if k in seen: continue
        seen.add(k); out.append(c)
    return out[:cap], len(out)

if __name__ == '__main__':
    import sys
    b = open(sys.argv[1]).read()
    sel, total = select(b)
    print(f'{total} claims selected (showing up to cap):')
    for i, c in enumerate(sel, 1): print(f'  C{i}: {c[:150]}')

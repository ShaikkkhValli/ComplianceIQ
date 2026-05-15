"""Parse regulatory citations into structured ClauseRef objects (rubric §5).

Recognises common forms:
    Regulation 4(2)(a)
    Reg. 4(2)(a)
    Section 12.3.1
    Sec. 12.3
    Para 7
    Article 5
    Clause 9(b)
    Schedule II
    Rule 6
    Page 14, Para 7

Output is the structured ClauseRef defined in models.py. The .canonical()
method on that class produces a stable string suitable for deduplicating
requirements that quote the same clause under different citation styles.
"""

from __future__ import annotations

import re

from complianceiq.models import ClauseRef


# Order matters: more-specific patterns first.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Regulation 4(2)(a) / Reg. 4(2)(a) / Reg 4(2)(a)
    (re.compile(r"\b(?:regulation|reg\.?)\s+(\d+(?:\([^)]+\))*)", re.I), "regulation"),
    # Section 12.3.1 / Sec. 12.3.1
    (re.compile(r"\b(?:section|sec\.?)\s+(\d+(?:\.\d+)*)", re.I), "section"),
    # Article 5(2)
    (re.compile(r"\barticle\s+(\d+(?:\([^)]+\))*)", re.I), "article"),
    # Clause 9(b)
    (re.compile(r"\bclause\s+(\d+(?:\([^)]+\))*)", re.I), "clause"),
    # Rule 6
    (re.compile(r"\brule\s+(\d+(?:\.\d+)*)", re.I), "rule"),
    # Para 7 / Paragraph 7
    (re.compile(r"\b(?:para(?:graph)?\.?)\s+(\d+(?:\.\d+)*)", re.I), "paragraph"),
    # Schedule II / Schedule 2
    (re.compile(r"\bschedule\s+([IVXLC]+|\d+)", re.I), "schedule"),
]

_PAGE_RE = re.compile(r"\bpage\s+(\d+)", re.I)
_SUB_RE  = re.compile(r"\(([^()]+)\)")


def _split_subclauses(token: str) -> tuple[str, list[str]]:
    """Split '4(2)(a)' into ('4', ['2','a']) and '12.3.1' into ('12', ['3','1'])."""
    token = token.strip()
    # Parenthesised form: 4(2)(a)
    if "(" in token:
        head = token.split("(", 1)[0]
        subs = _SUB_RE.findall(token)
        return head, [s.strip() for s in subs]
    # Dotted form: 12.3.1
    if "." in token:
        parts = token.split(".")
        return parts[0], parts[1:]
    return token, []


def parse_clause_ref(text: str) -> ClauseRef | None:
    """Find the first clause-citation in `text` and return a ClauseRef.

    Returns None when no recognised citation is present.
    """
    if not text:
        return None
    page_match = _PAGE_RE.search(text)
    page = int(page_match.group(1)) if page_match else None

    for pat, _label in _PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        token = m.group(1)
        article, subs = _split_subclauses(token)
        return ClauseRef(
            raw=m.group(0).strip(),
            article=article,
            sub_clauses=subs,
            page=page,
        )
    return None

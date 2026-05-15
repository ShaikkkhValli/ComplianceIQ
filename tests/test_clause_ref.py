"""Unit tests for the ClauseRef parser (rubric §5: domain extraction)."""

import pytest

from complianceiq.utils.clause_ref import parse_clause_ref


@pytest.mark.parametrize("text, expected_article, expected_subs", [
    ("Regulation 4(2)(a) of the IRDAI rules",  "4",  ["2", "a"]),
    ("Reg. 4(2)(a)",                            "4",  ["2", "a"]),
    ("As per Section 12.3.1 of the policy",     "12", ["3", "1"]),
    ("See Sec. 12.3 below",                     "12", ["3"]),
    ("Article 5(2)",                            "5",  ["2"]),
    ("Clause 9(b) shall apply",                 "9",  ["b"]),
    ("Para 7 of Schedule II",                   "7",  []),
    ("Rule 6 of MAS Notice",                    "6",  []),
    ("Paragraph 3.2 of the directive",          "3",  ["2"]),
])
def test_parse_clause_ref(text, expected_article, expected_subs):
    ref = parse_clause_ref(text)
    assert ref is not None, f"Expected a ClauseRef for {text!r}"
    assert ref.article == expected_article
    assert ref.sub_clauses == expected_subs


def test_parse_clause_ref_returns_none_for_no_citation():
    assert parse_clause_ref("This sentence has no citation.") is None
    assert parse_clause_ref("") is None


def test_canonical_form_dedupes_equivalent_citations():
    a = parse_clause_ref("Regulation 4(2)(a)")
    b = parse_clause_ref("Reg. 4(2)(a) of the same chapter")
    assert a is not None and b is not None
    assert a.canonical() == b.canonical() == "4.2.a"


def test_page_extraction():
    ref = parse_clause_ref("Section 12.3, page 47 of the regulation")
    assert ref is not None
    assert ref.page == 47

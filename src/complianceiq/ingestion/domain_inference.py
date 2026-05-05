"""Compliance domain inference from filenames.

Uses a priority-ordered keyword list so the most specific match wins
(e.g. 'reinsurance' beats 'insurance', 'cyber' beats 'information').
"""

from __future__ import annotations

import os

from complianceiq.models import Domain


# Order matters: earlier entries win ties. Place specific terms before generic.
_DOMAIN_RULES: list[tuple[str, Domain]] = [
    # Highly specific terms first
    ("reinsurance",  Domain.REINSURANCE),
    ("underwriting", Domain.UNDERWRITING),
    ("grievance",    Domain.CLAIMS_MANAGEMENT),
    ("claims",       Domain.CLAIMS_MANAGEMENT),
    ("fraud",        Domain.FRAUD_PREVENTION),
    ("audit",        Domain.INTERNAL_AUDIT),
    ("governance",   Domain.CORPORATE_GOVERNANCE),
    ("cyber",        Domain.INFORMATION_SECURITY),
    ("information security", Domain.INFORMATION_SECURITY),
    ("infosec",      Domain.INFORMATION_SECURITY),
    ("investment",   Domain.INVESTMENT_MANAGEMENT),
    ("marketing",    Domain.SALES_DISTRIBUTION),
    ("distribution", Domain.SALES_DISTRIBUTION),
    ("sales",        Domain.SALES_DISTRIBUTION),
    ("risk",         Domain.RISK_MANAGEMENT),
]


def infer_domain(file_path: str | os.PathLike) -> Domain:
    """Infer the compliance domain from a file path.

    Matching is done against the basename only, so a parent directory
    containing a domain keyword will not bleed into unrelated files.
    """
    name = os.path.basename(str(file_path)).lower()
    for keyword, domain in _DOMAIN_RULES:
        if keyword in name:
            return domain
    return Domain.GENERAL

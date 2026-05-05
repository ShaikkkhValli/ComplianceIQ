"""Domain inference is deterministic — verify priority order and edge cases."""

from complianceiq.ingestion.domain_inference import infer_domain
from complianceiq.models import Domain


def test_reinsurance_beats_insurance():
    assert infer_domain("Specimen Reinsurance Agreement.docx") == Domain.REINSURANCE


def test_cyber_beats_information():
    # 'cyber' has higher priority than 'information' in the rule list
    assert infer_domain("Cyber Insurance Policy Document.docx") == Domain.INFORMATION_SECURITY


def test_information_security_phrase_match():
    assert infer_domain("Information security Guidelines.pdf") == Domain.INFORMATION_SECURITY


def test_governance():
    assert infer_domain("Governance and Corporate Structure.docx") == Domain.CORPORATE_GOVERNANCE


def test_risk_management():
    assert infer_domain("Risk Management and Compliance.docx") == Domain.RISK_MANAGEMENT


def test_audit():
    assert infer_domain("Audit Control for Insurance Companies.pdf") == Domain.INTERNAL_AUDIT


def test_fraud():
    assert infer_domain("fraud-risk-framework.pdf") == Domain.FRAUD_PREVENTION


def test_underwriting():
    assert infer_domain("Underwriting and Risk Assessment.docx") == Domain.UNDERWRITING


def test_grievance_to_claims():
    assert infer_domain("Grievance Redressal Policy.pdf") == Domain.CLAIMS_MANAGEMENT


def test_unknown_falls_back_to_general():
    assert infer_domain("totally-random-filename.pdf") == Domain.GENERAL


def test_basename_only_does_not_leak_from_parent_dir():
    # Even if the parent dir contains 'risk', the basename wins
    assert infer_domain("/data/risk_dir/cyber-policy.pdf") == Domain.INFORMATION_SECURITY

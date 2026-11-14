"""Re-export: evidence eligibility lives in app/domain/eligibility.py (shared by RAG, APIs, Data Platform)."""

from app.domain.eligibility import (  # noqa: F401
    USABLE_ELIGIBILITY,
    Eligibility,
    EligibilityPolicy,
    SourceDecision,
    decisions_path,
    registry_path,
    resolve,
)

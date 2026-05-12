"""
Compliance Change Control — Validation Rules.

Source: COMPLIANCE_CHANGE_CONTROL_RULES.md §1, §2, §9, §10
       COMPLIANCE_CHANGE_CONTROL_PROCESS.md §D, §E, §F

Every validation function returns a list of issue dicts:
    {"severity": "BLOCKING"|"WARNING", "message": str, "rule": str}
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .models import (
    ChangeRequest,
    ChangeType,
    CRStatus,
    ImpactLevel,
    RequirementLinkageType,
    RootCauseCategory,
    VerificationType,
)


# ---------------------------------------------------------------------------
# ID Pattern Registry  —  C-PROCESS §B, C-RULES §4
# ---------------------------------------------------------------------------

ID_PATTERNS: Dict[str, str] = {
    "CR": r"^CR-[0-9]{3,}$",
    "SYS-REQ": r"^SYS-REQ-[0-9]+$",
    "SW-REQ": r"^SW-REQ-[0-9]+$",
    "SW-ARCH": r"^SW-ARCH-[0-9]+$",
    "TC-UT": r"^TC-UT-[0-9]+$",
    "TC-SIT": r"^TC-SIT-[0-9]+$",
    "TC-SVT": r"^TC-SVT-[0-9]+$",
    "TC-SYSIT": r"^TC-SYSIT-[0-9]+$",
    "TC-SYST": r"^TC-SYST-[0-9]+$",
}

# VerificationCase type → valid ID prefix mapping  — C-PROCESS §F.3
VC_TYPE_PREFIX_MAP: Dict[VerificationType, str] = {
    VerificationType.UNIT: "TC-UT-",
    VerificationType.SOFTWARE_INTEGRATION: "TC-SIT-",
    VerificationType.SOFTWARE_VERIFICATION: "TC-SVT-",
    VerificationType.SYSTEM_INTEGRATION: "TC-SYSIT-",
    VerificationType.SYSTEM_VERIFICATION: "TC-SYST-",
}

# Requirement level → required VerificationType  — C-PROCESS §D.4
REQ_VC_TYPE_MAP: Dict[str, List[VerificationType]] = {
    "SYS-REQ": [VerificationType.SYSTEM_VERIFICATION],
    "SW-REQ": [VerificationType.SOFTWARE_VERIFICATION],
    "SW-ARCH": [VerificationType.SOFTWARE_INTEGRATION, VerificationType.SYSTEM_INTEGRATION],
}


class CRValidator:
    """Implements validation rules from C-RULES and C-PROCESS."""

    # ── ID Format ────────────────────────────────────────────────────────

    def validate_id_format(self, ref: str) -> Tuple[bool, str]:
        """Validate an arbitrary ID against known patterns.

        Returns (is_valid, prefix_or_error_message).
        """
        for prefix, pattern in ID_PATTERNS.items():
            if re.match(pattern, ref):
                return True, prefix
        return False, f"Invalid ID format: {ref}"

    def classify_requirement_id(self, ref: str) -> Optional[str]:
        """Return the prefix class (SYS-REQ, SW-REQ, SW-ARCH) or None."""
        valid, prefix = self.validate_id_format(ref)
        if valid and prefix in ("SYS-REQ", "SW-REQ", "SW-ARCH"):
            return prefix
        return None

    # ── Impact Classification  —  C-PROCESS §E.1 ────────────────────────

    def validate_impact_classification(self, cr: ChangeRequest) -> List[dict]:
        """Detect impact level from requirement refs and flag mismatches."""
        issues: List[dict] = []
        detected: set[str] = set()

        for ref in cr.requirement_refs:
            prefix = self.classify_requirement_id(ref)
            if prefix == "SYS-REQ":
                detected.add("SYS")
            elif prefix == "SW-ARCH":
                detected.add("ARCH")
            elif prefix == "SW-REQ":
                detected.add("SW")

        # Check code-file paths
        for ref in cr.requirement_refs:
            if any(ref.startswith(p) for p in ("src/", "lib/", "app/")):
                detected.add("CODE")

        # Verify declared impact_level covers detected levels
        declared = {il.value for il in cr.impact_level}
        for level in detected:
            if level not in declared:
                issues.append({
                    "severity": "WARNING",
                    "message": f"{level} impact detected from refs but not in impact_level",
                    "rule": "C-PROCESS §E.1: auto-detect impact from requirement refs",
                })

        return issues

    # ── Derivation Obligations  —  C-PROCESS §F.1 ───────────────────────

    def validate_derivation_obligations(self, cr: ChangeRequest) -> List[dict]:
        """Check parent→child derivation rules."""
        issues: List[dict] = []

        sys_reqs = [r for r in cr.requirement_refs if r.startswith("SYS-REQ-")]
        sw_reqs = [r for r in cr.requirement_refs if r.startswith("SW-REQ-")]

        # SYS-REQ must have SW-REQ children (1-7)  — C-PROCESS §F.1
        if sys_reqs and not sw_reqs:
            issues.append({
                "severity": "BLOCKING",
                "message": "SYS-REQ present but no SW-REQ (derivation obligation)",
                "rule": "C-PROCESS §F.1: SYS-REQ MUST derive 1-7 SW-REQs",
            })

        return issues

    # ── Bugfix Rules  —  C-RULES §9, §10 ────────────────────────────────

    def validate_bugfix_rules(self, cr: ChangeRequest) -> List[dict]:
        """Validate bugfix-specific rules from C-RULES §9."""
        issues: List[dict] = []

        if cr.change_type != ChangeType.BUGFIX:
            return issues

        sw_reqs = [r for r in cr.requirement_refs if r.startswith("SW-REQ-")]

        # §9.1 / §9.6: bugfix must have SW-REQ linkage
        if not sw_reqs:
            issues.append({
                "severity": "BLOCKING",
                "message": "Bugfix CR has no SW-REQ in requirement_refs",
                "rule": "C-RULES §9.1: Every functional bugfix links to SW-REQ",
            })

        # §9.7: bugfix must declare requirement_linkage_type
        if cr.requirement_linkage_type is None:
            issues.append({
                "severity": "BLOCKING",
                "message": "Bugfix CR missing requirement_linkage_type",
                "rule": "C-RULES §9.7: bugfix must declare linkage type",
            })

        # §9.3 / §9.6: new_ref requires APPROVED new SW-REQ before past SUBMITTED
        if cr.requirement_linkage_type == RequirementLinkageType.NEW_REF:
            if cr.status not in (CRStatus.DRAFT, CRStatus.EMERGENCY):
                # At SUBMITTED+, the new SW-REQ must be APPROVED
                # (we can't verify external requirement state here,
                #  but we flag the obligation)
                if not sw_reqs:
                    issues.append({
                        "severity": "BLOCKING",
                        "message": "Bugfix with new_ref but no SW-REQ linked",
                        "rule": "C-RULES §9.3: new SW-REQ must derive through DRAFT→APPROVED "
                                "before CR transitions past SUBMITTED",
                    })

        # §9.4 / §9.6: at IMPLEMENTED, must have affected_verifications
        if cr.status == CRStatus.IMPLEMENTED and not cr.affected_verifications:
            issues.append({
                "severity": "BLOCKING",
                "message": "Bugfix CR at IMPLEMENTED with no VerificationCases",
                "rule": "C-RULES §9.4: at least one regression VerificationCase per SW-REQ",
            })

        # §9.5: emergency bugfix rules
        if cr.is_emergency:
            if not cr.incident_id:
                issues.append({
                    "severity": "BLOCKING",
                    "message": "Emergency bugfix CR missing incident_id",
                    "rule": "C-RULES §9.5: incident_id is mandatory for EMERGENCY CRs",
                })

        # §8.1: root_cause_category required at CLOSED for bugfix
        if cr.status == CRStatus.CLOSED and cr.root_cause_category is None:
            issues.append({
                "severity": "BLOCKING",
                "message": "Bugfix CR at CLOSED without root_cause_category",
                "rule": "C-RULES §8.1: root_cause_category documented for bugfix",
            })

        # §9.6 WARNING: SW-REQ in DRAFT
        if cr.requirement_linkage_type == RequirementLinkageType.UPDATED_REF:
            issues.append({
                "severity": "WARNING",
                "message": "Bugfix with updated_ref — verify SW-REQ moved to DRAFT and re-approved",
                "rule": "C-RULES §9.6: warns when linked SW-REQ is in DRAFT",
            })

        return issues

    # ── Emergency Rules  —  C-PROCESS §I, C-RULES §9.5 ──────────────────

    def validate_emergency_rules(self, cr: ChangeRequest) -> List[dict]:
        """Validate emergency-specific rules."""
        issues: List[dict] = []

        if not cr.is_emergency:
            return issues

        if not cr.incident_id:
            issues.append({
                "severity": "BLOCKING",
                "message": "Emergency CR missing incident_id",
                "rule": "C-PROCESS §I.2: incident_id required",
            })

        # E→S transition requires post_mortem_date
        if cr.status == CRStatus.EMERGENCY and cr.post_mortem_date is None:
            issues.append({
                "severity": "BLOCKING",
                "message": "Emergency CR missing post_mortem_date before submit",
                "rule": "C-PROCESS §I.2: post-mortem date MUST be committed at E→S",
            })

        return issues

    # ── Verification Type Mapping  —  C-PROCESS §D.4, §F.3 ──────────────

    def validate_verification_type_mapping(
        self, vc_type: VerificationType, req_id: str
    ) -> Tuple[bool, str]:
        """Check that a VerificationCase type matches the requirement level."""
        prefix = self.classify_requirement_id(req_id)
        if prefix is None:
            return True, "Non-requirement reference — type mapping not enforced"

        allowed = REQ_VC_TYPE_MAP.get(prefix, [])
        if vc_type in allowed:
            return True, f"Type {vc_type.value} matches {prefix}"

        allowed_str = " or ".join(t.value for t in allowed)
        return False, (
            f"VerificationCase type '{vc_type.value}' does not match "
            f"requirement level '{prefix}' (expected: {allowed_str})"
        )

    # ── Full Validation ──────────────────────────────────────────────────

    def validate_all(self, cr: ChangeRequest) -> List[dict]:
        """Run all validation rules and return combined issues."""
        issues: List[dict] = []
        issues.extend(self.validate_impact_classification(cr))
        issues.extend(self.validate_derivation_obligations(cr))
        issues.extend(self.validate_bugfix_rules(cr))
        issues.extend(self.validate_emergency_rules(cr))
        return issues

    def validate_for_transition(self, cr: ChangeRequest, target: CRStatus) -> List[dict]:
        """Run validations relevant to a specific target state."""
        issues: List[dict] = []

        # Always check impact and derivation
        issues.extend(self.validate_impact_classification(cr))
        issues.extend(self.validate_derivation_obligations(cr))

        # Bugfix rules are relevant from SUBMITTED onward
        if target not in (CRStatus.DRAFT, CRStatus.EMERGENCY):
            issues.extend(self.validate_bugfix_rules(cr))

        # Emergency rules
        if cr.is_emergency:
            issues.extend(self.validate_emergency_rules(cr))

        return issues

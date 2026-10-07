from __future__ import annotations
from typing import List
from guardian_ai.core.models import (
    RepoMetadata,
    CodePatch,
    TestOutcome,
    RegressionVerification,
    RiskAssessment,
)

class RiskScorer:
    def __init__(self, metadata: RepoMetadata):
        self.metadata = metadata

    def assess_risk(
        self,
        patches: List[CodePatch],
        baseline: TestOutcome,
        post_tests: TestOutcome,
        regression: RegressionVerification
    ) -> RiskAssessment:
        risk_score = 5.0
        risk_factors: List[str] = []
        confidence_score = 40.0
        confidence_evidence: List[str] = []

        # 1. Evaluate surface of files changed
        total_callers = 0
        diff_lines = 0
        for p in patches:
            diff_lines += len(p.unified_diff.splitlines())
            fa = self.metadata.file_index.get(p.file_path)
            if fa:
                for sym in fa.symbols:
                    total_callers += len(sym.callers)

            # Check if file is a shared utility or central config
            if any(core_kw in p.file_path.lower() for core_kw in ["config", "util", "common", "base", "core"]):
                risk_score += 10.0
                risk_factors.append(f"Modified shared module '{p.file_path}' (+10% risk)")

        # Evaluate fan-out
        if total_callers > 6:
            risk_score += 15.0
            risk_factors.append(f"High caller fan-out: {total_callers} dependent functions depend on modified symbols (+15% risk)")
        elif total_callers > 0:
            risk_factors.append(f"Controlled fan-out: {total_callers} dependent caller(s)")

        # Evaluate diff minimality
        if diff_lines > 40:
            risk_score += 15.0
            risk_factors.append(f"Elevated diff volume ({diff_lines} lines changed) (+15% risk)")
        else:
            confidence_evidence.append(f"Surgical patch: diff contains only {diff_lines} lines")
            confidence_score += 10.0

        # 2. Test Verification Evidence
        if baseline.passed > 0:
            confidence_evidence.append(f"Baseline verified: {baseline.passed} tests passed prior to modification")
            confidence_score += 15.0

        if len(regression.fixed_tests) > 0 or post_tests.passed > baseline.passed:
            confidence_evidence.append(f"Bugfix verified: {len(regression.fixed_tests) or (post_tests.passed - baseline.passed)} previously failing or new test(s) now pass")
            confidence_score += 15.0

        if not regression.regression_detected:
            confidence_evidence.append(f"Zero regressions detected across entire test suite ({post_tests.passed} tests passing)")
            confidence_score += 15.0
        else:
            risk_score += 35.0
            risk_factors.append(f"Active regressions detected: {len(regression.newly_failed_tests)} test(s) failed after patch (+35% risk)")
            confidence_score = max(5.0, confidence_score - 30.0)

        # 3. Static 6-layer validation evidence
        all_passed_checks = all(p.hallucination_check_passed for p in patches)
        if all_passed_checks and patches:
            confidence_evidence.append("Passed all 6 static validation layers (syntax, imports, symbols, dependencies, diff safety)")
            confidence_score += 10.0
        else:
            risk_score += 20.0
            risk_factors.append("One or more static validation layers failed or produced warnings (+20% risk)")

        # Cap scores to realistic bounds
        final_risk = min(95.0, max(5.0, round(risk_score, 1)))
        final_confidence = min(96.0, max(10.0, round(confidence_score, 1)))

        return RiskAssessment(
            regression_risk_percentage=final_risk,
            solution_confidence_percentage=final_confidence,
            risk_factors=risk_factors or ["Surgical change with isolated scope"],
            confidence_evidence=confidence_evidence
        )

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
        risk_score = 10.0
        risk_factors: List[str] = []
        confidence_score = 50.0
        confidence_evidence: List[str] = []

        # 1. Evaluate files changed
        total_callers = 0
        for p in patches:
            fa = self.metadata.file_index.get(p.file_path)
            if fa:
                for sym in fa.symbols:
                    total_callers += len(sym.callers)
            
            # Check if file is shared config or core utility
            if any(core_kw in p.file_path.lower() for core_kw in ["config", "util", "common", "base", "core"]):
                risk_score += 15.0
                risk_factors.append(f"Modified shared module '{p.file_path}'")

        if total_callers > 5:
            risk_score += 15.0
            risk_factors.append(f"High fan-out: modified module is called by {total_callers} dependent functions/callers")
        elif total_callers > 0:
            risk_factors.append(f"Moderate caller fan-out ({total_callers} callers detected)")

        # 2. Evaluate diff size
        diff_lines = sum(len(p.unified_diff.splitlines()) for p in patches)
        if diff_lines > 50:
            risk_score += 20.0
            risk_factors.append(f"Large diff size ({diff_lines} lines changed)")
        else:
            confidence_evidence.append(f"Minimal surgical change ({diff_lines} lines in diff)")

        # 3. Test verification evidence
        if baseline.passed > 0:
            confidence_evidence.append(f"Baseline verified: {baseline.passed} existing tests passed prior to modification")
            confidence_score += 15.0

        if not regression.regression_detected:
            confidence_evidence.append(f"Zero regressions detected across entire test suite ({post_tests.passed} tests passing)")
            confidence_score += 25.0
            risk_score = max(5.0, risk_score - 10.0)
        else:
            risk_score += 40.0
            risk_factors.append(f"Regressions detected: {len(regression.newly_failed_tests)} test(s) failed after patch")
            confidence_score = max(10.0, confidence_score - 35.0)

        # 4. Anti-hallucination check
        all_passed_checks = all(p.hallucination_check_passed for p in patches)
        if all_passed_checks:
            confidence_evidence.append("AST static verification confirmed 100% of symbols, imports, and calls are valid")
            confidence_score += 10.0
        else:
            risk_score += 25.0
            risk_factors.append("Patch contained unverified imports or syntax warnings")

        final_risk = min(100.0, max(0.0, round(risk_score, 1)))
        final_confidence = min(100.0, max(0.0, round(confidence_score, 1)))

        return RiskAssessment(
            regression_risk_percentage=final_risk,
            solution_confidence_percentage=final_confidence,
            risk_factors=risk_factors or ["Minimal change with isolated scope"],
            confidence_evidence=confidence_evidence
        )

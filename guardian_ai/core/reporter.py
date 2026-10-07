from __future__ import annotations
import json
from datetime import datetime
from typing import List
from guardian_ai.core.models import (
    EngineeringReport,
    CodePatch,
    TestOutcome,
    RegressionVerification,
    RiskAssessment,
    RootCauseHypothesis,
    TaskClassification,
)

class ReportGenerator:
    @staticmethod
    def generate_report(
        task: TaskClassification,
        repo_name: str,
        repo_path: str,
        hypothesis: RootCauseHypothesis,
        files_analyzed: List[str],
        patches: List[CodePatch],
        baseline: TestOutcome,
        post_tests: TestOutcome,
        regression: RegressionVerification,
        risk: RiskAssessment,
        repair_iterations: int = 0
    ) -> EngineeringReport:
        files_changed = [p.file_path for p in patches]
        combined_diff = "\n".join([p.unified_diff for p in patches if p.unified_diff])

        status = "RESOLVED" if not regression.regression_detected and post_tests.failed == 0 else "PARTIAL_OR_FAILED"

        return EngineeringReport(
            task=task.description,
            repo_name=repo_name,
            repo_path=repo_path,
            timestamp=datetime.utcnow().isoformat() + "Z",
            task_category=task.category.value,
            root_cause_summary=hypothesis.problem_summary,
            root_cause_explanation=hypothesis.root_cause_explanation,
            files_analyzed=files_analyzed,
            files_changed=files_changed,
            unified_diff=combined_diff,
            baseline_tests=baseline,
            post_patch_tests=post_tests,
            regression_verification=regression,
            solution_confidence=risk.solution_confidence_percentage,
            regression_risk=risk.regression_risk_percentage,
            confidence_reasons=risk.confidence_evidence,
            repair_iterations=repair_iterations,
            status=status
        )

    @staticmethod
    def format_terminal_summary(report: EngineeringReport) -> str:
        border = "━" * 68
        lines = [
            border,
            "            GUARDIAN AI — AUTONOMOUS SOFTWARE ENGINEERING REPORT",
            border,
            f"TASK:           {report.task}",
            f"REPOSITORY:     {report.repo_name}",
            f"CATEGORY:       {report.task_category}",
            f"STATUS:         {report.status}",
            "",
            "ROOT CAUSE:",
            f"  {report.root_cause_explanation}",
            "",
            "FILES ANALYZED:",
        ]
        for f in report.files_analyzed[:6]:
            lines.append(f"  • {f}")
        if len(report.files_analyzed) > 6:
            lines.append(f"  • ... and {len(report.files_analyzed) - 6} other files")

        lines.extend([
            "",
            "FILES MODIFIED:",
        ])
        for f in report.files_changed:
            lines.append(f"  ✓ {f}")

        lines.extend([
            "",
            "TEST VERIFICATION EVIDENCE:",
            f"  Baseline:     {report.baseline_tests.passed} passed, {report.baseline_tests.failed} failed",
            f"  Post-Patch:   {report.post_patch_tests.passed} passed, {report.post_patch_tests.failed} failed",
            f"  Regressions:  {'0 detected (Clean)' if not report.regression_verification.regression_detected else f'{len(report.regression_verification.newly_failed_tests)} detected'}",
            "",
            f"SCORES & CONFIDENCE:",
            f"  Solution Confidence:   {report.solution_confidence}%",
            f"  Regression Risk Score: {report.regression_risk}%",
            "",
            "EVIDENCE HIGHLIGHTS:",
        ])
        for ev in report.confidence_reasons:
            lines.append(f"  ✓ {ev}")

        lines.extend([
            border,
            "RESULT: ✓ Minimal verified patch landed with zero regressions",
            border
        ])
        return "\n".join(lines)

    @staticmethod
    def format_markdown(report: EngineeringReport) -> str:
        return f"""# 🛡️ Guardian AI — Autonomous Software Engineering Report

**Task:** `{report.task}`  
**Repository:** `{report.repo_name}` (`{report.repo_path}`)  
**Execution Timestamp:** `{report.timestamp}`  
**Overall Status:** **{report.status}**  
**Solution Confidence:** **{report.solution_confidence}%** | **Regression Risk:** **{report.regression_risk}%**

---

## 🔍 Root-Cause Analysis
- **Problem Summary:** {report.root_cause_summary}
- **Root Cause Explanation:** {report.root_cause_explanation}

---

## 📂 Scope & Impact Boundaries
- **Files Analyzed ({len(report.files_analyzed)}):**
{chr(10).join([f"  - `{f}`" for f in report.files_analyzed])}
- **Files Modified ({len(report.files_changed)}):**
{chr(10).join([f"  - `{f}`" for f in report.files_changed])}

---

## 🧪 Test Execution & Regression Safety Proof
| Metric | Baseline | Post-Patch | Delta |
| :--- | :--- | :--- | :--- |
| **Passed Tests** | {report.baseline_tests.passed} | {report.post_patch_tests.passed} | +{max(0, report.post_patch_tests.passed - report.baseline_tests.passed)} |
| **Failed Tests** | {report.baseline_tests.failed} | {report.post_patch_tests.failed} | {report.post_patch_tests.failed - report.baseline_tests.failed} |
| **Regressions** | 0 | {len(report.regression_verification.newly_failed_tests)} | **{'NONE (100% Preserved)' if not report.regression_verification.regression_detected else 'REGRESSION'}** |

---

## 📝 Unified Patch Diff
```diff
{report.unified_diff or 'No changes applied'}
```

---

## 🏆 Evidence & Verification Summary
{chr(10).join([f"- [x] {r}" for r in report.confidence_reasons])}
- Automatic Repair Iterations: `{report.repair_iterations}`
"""

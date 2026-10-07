from __future__ import annotations
import os
import time
from typing import Callable, List, Optional
from guardian_ai.core.models import (
    EngineeringReport,
    ExecutionTraceStep,
    RepoMetadata,
    StepStatus,
    TaskClassification,
    RootCauseHypothesis,
    CodePatch,
    TestOutcome,
    RegressionVerification,
    RiskAssessment,
    ImpactGraph,
)
from guardian_ai.core.analyzer import RepositoryAnalyzer
from guardian_ai.core.search import CodeSearchEngine
from guardian_ai.core.git_ops import GitOperations
from guardian_ai.core.test_runner import TestRunner
from guardian_ai.core.task_classifier import TaskClassifier
from guardian_ai.core.root_cause import RootCauseAnalyzer
from guardian_ai.core.impact_analyzer import ImpactAnalyzer
from guardian_ai.core.patcher import PatchGenerator
from guardian_ai.core.risk_scorer import RiskScorer
from guardian_ai.core.reporter import ReportGenerator
from guardian_ai.core.security import SecurityGuard
from guardian_ai.providers.base import LLMProvider
from guardian_ai.providers.factory import get_llm_provider

EventCallback = Callable[[ExecutionTraceStep], None]

class GuardianAgent:
    def __init__(
        self,
        repo_path: str,
        provider: Optional[LLMProvider] = None,
        max_repair_iterations: int = 3,
        event_callback: Optional[EventCallback] = None
    ):
        self.repo_path = os.path.abspath(repo_path)
        self.repo_name = os.path.basename(self.repo_path)
        self.provider = provider or get_llm_provider()
        self.max_repair_iterations = max_repair_iterations
        self.event_callback = event_callback
        self.trace: List[ExecutionTraceStep] = []

        self.analyzer = RepositoryAnalyzer(self.repo_path)
        self.git_ops = GitOperations(self.repo_path)
        self.metadata: Optional[RepoMetadata] = None
        self.search_engine: Optional[CodeSearchEngine] = None
        self.test_runner: Optional[TestRunner] = None
        self.impact_analyzer: Optional[ImpactAnalyzer] = None

    def _emit(self, step_id: str, name: str, status: StepStatus, details: str = "", duration_ms: float = 0.0):
        step = ExecutionTraceStep(
            step_id=step_id,
            name=name,
            status=status,
            details=details,
            duration_ms=duration_ms
        )
        self.trace.append(step)
        if self.event_callback:
            try:
                self.event_callback(step)
            except Exception:
                pass

    def run(self, user_request: str) -> EngineeringReport:
        t_start = time.time()
        
        # Security sanitization of task prompt
        sanitized_request, sec_warnings = SecurityGuard.sanitize_untrusted_context(user_request)
        init_details = f"Request: {sanitized_request}"
        if sec_warnings:
            init_details += f" [Security Defense: {len(sec_warnings)} injection attempt(s) defused]"

        self._emit("TASK_INIT", "Task Initialized", StepStatus.SUCCESS, init_details)

        # 1. Repository Discovery & AST Analysis
        t0 = time.time()
        self._emit("REPO_SCAN", "Repository Discovery & AST Analysis", StepStatus.RUNNING, "Scanning repository structure, symbols, imports, and tests...")
        self.metadata = self.analyzer.analyze()
        self.search_engine = CodeSearchEngine(self.metadata)
        self.test_runner = TestRunner(self.repo_path, default_command=self.metadata.test_command)
        self.impact_analyzer = ImpactAnalyzer(self.metadata)
        dur = (time.time() - t0) * 1000
        self._emit(
            "REPO_SCAN",
            "Repository Discovery & AST Analysis",
            StepStatus.SUCCESS,
            f"Discovered {self.metadata.total_files} files ({self.metadata.primary_language}). Framework: {', '.join(self.metadata.frameworks) or 'None'}. Tests: {len(self.metadata.test_files)} files.",
            duration_ms=dur
        )

        # 2. Baseline Test Execution
        t0 = time.time()
        self._emit("TEST_BASELINE", "Record Pre-Modification Test Baseline", StepStatus.RUNNING, "Running existing test suite to establish regression baseline...")
        baseline_test = self.test_runner.run_tests()
        dur = (time.time() - t0) * 1000
        self._emit(
            "TEST_BASELINE",
            "Record Pre-Modification Test Baseline",
            StepStatus.SUCCESS,
            f"Baseline recorded: {baseline_test.passed} passed, {baseline_test.failed} failed, {baseline_test.skipped} skipped.",
            duration_ms=dur
        )

        # 3. Task Classification & Code Partitioning
        t0 = time.time()
        self._emit("TASK_CLASSIFY", "Task Classification & Impact Scope Boundary", StepStatus.RUNNING, "Classifying request and isolating directly relevant vs unaffected files...")
        classifier = TaskClassifier(self.metadata, self.search_engine, self.provider)
        task_plan = classifier.classify(sanitized_request)
        dur = (time.time() - t0) * 1000
        self._emit(
            "TASK_CLASSIFY",
            "Task Classification & Impact Scope Boundary",
            StepStatus.SUCCESS,
            f"Category: {task_plan.category.value}. Relevant: {', '.join(task_plan.directly_relevant_files)}. Protected/Unrelated: {len(task_plan.unrelated_files)} files.",
            duration_ms=dur
        )

        # 4. Dependency & Impact Analysis (Callers, Transitive Callees, Related Tests)
        t0 = time.time()
        self._emit("IMPACT_ANALYSIS", "Dependency & Call-Graph Impact Traversal", StepStatus.RUNNING, "Tracing direct & indirect callers and affected test suites...")
        impact = self.impact_analyzer.analyze_impact(task_plan.directly_relevant_files, task_plan.target_symbols)
        dur = (time.time() - t0) * 1000
        self._emit(
            "IMPACT_ANALYSIS",
            "Dependency & Call-Graph Impact Traversal",
            StepStatus.SUCCESS,
            f"Impact mapped: {len(impact.direct_callers)} direct callers, {len(impact.indirect_callers)} transitive callers, {len(impact.affected_tests)} linked test files.",
            duration_ms=dur
        )

        # 5. Code Search & Context Assembly
        t0 = time.time()
        self._emit("CODE_SEARCH", "Intelligent Code Retrieval & Context Assembly", StepStatus.RUNNING, "Retrieving minimal context snippets via AST symbol references...")
        search_results = self.search_engine.search(sanitized_request, top_k=4)
        context_snippets = "\n\n".join([f"File: {r.file_path}\n{r.snippet}" for r in search_results])
        dur = (time.time() - t0) * 1000
        self._emit(
            "CODE_SEARCH",
            "Intelligent Code Retrieval & Context Assembly",
            StepStatus.SUCCESS,
            f"Retrieved {len(search_results)} relevant code units without bloating context window.",
            duration_ms=dur
        )

        # 6. Root Cause Analysis
        t0 = time.time()
        self._emit("ROOT_CAUSE", "Evidence-Driven Root-Cause Analysis", StepStatus.RUNNING, "Formulating hypothesis and safe patch strategy...")
        rc_analyzer = RootCauseAnalyzer(self.metadata, self.provider)
        hypothesis = rc_analyzer.analyze(task_plan, baseline_test, file_snippets=context_snippets)
        dur = (time.time() - t0) * 1000
        self._emit(
            "ROOT_CAUSE",
            "Evidence-Driven Root-Cause Analysis",
            StepStatus.SUCCESS,
            f"Root cause identified: {hypothesis.problem_summary}. Strategy: {hypothesis.safe_patch_strategy}",
            duration_ms=dur
        )

        # 7. Safety Checkpoint & Git Preparation
        self.git_ops.create_safety_checkpoint("guardian_pre_patch")

        # 8. Patch Generation & Automated Repair Loop (supports multi-file changes)
        patcher = PatchGenerator(self.metadata, self.provider)
        candidate_files = task_plan.directly_relevant_files or (self.metadata.source_files[:1] if self.metadata.source_files else [])
        
        applied_patches: List[CodePatch] = []
        iteration = 0
        success = False
        post_tests = baseline_test
        failure_feedback = None

        while iteration < self.max_repair_iterations and not success:
            iteration += 1
            t0 = time.time()
            self._emit(
                f"PATCH_CYCLE_{iteration}",
                f"Patch Synthesis & 6-Layer Validation (Attempt {iteration})",
                StepStatus.RUNNING,
                f"Generating and validating patch across relevant files: {', '.join(candidate_files)}..."
            )

            current_iteration_patches: List[CodePatch] = []
            for target_file in candidate_files:
                patch = patcher.generate_patch(task_plan, hypothesis, target_file, failure_feedback=failure_feedback)
                if patch and patch.hallucination_check_passed:
                    applied = patcher.apply_patch_to_disk(patch)
                    if applied:
                        current_iteration_patches.append(patch)

            if not current_iteration_patches:
                self._emit(
                    f"PATCH_CYCLE_{iteration}",
                    f"Patch Synthesis & 6-Layer Validation (Attempt {iteration})",
                    StepStatus.FAILED,
                    f"No valid patches passed all 6 validation layers."
                )
                break

            applied_patches = current_iteration_patches
            dur = (time.time() - t0) * 1000
            self._emit(
                f"PATCH_CYCLE_{iteration}",
                f"Patch Landed & Verified (Attempt {iteration})",
                StepStatus.SUCCESS,
                f"Patched {len(applied_patches)} file(s). Passed 6 static validation layers (syntax, imports, symbols, dependencies, diff safety).",
                duration_ms=dur
            )

            # Step 8A: Targeted Tests First (Fast-fail)
            t0 = time.time()
            if impact.affected_tests:
                target_test = impact.affected_tests[0]
                self._emit("TARGETED_TESTS", "Run Targeted Tests", StepStatus.RUNNING, f"Executing targeted test suite '{target_test}'...")
                targeted_outcome = self.test_runner.run_tests(target_test_file=target_test)
                if targeted_outcome.failed > 0:
                    self._emit("TARGETED_TESTS", "Targeted Test Failure", StepStatus.FAILED, f"Targeted tests failed ({targeted_outcome.failed} failed).")
                    failure_feedback = f"Targeted test failure:\n{targeted_outcome.output[-800:]}"
                    self.git_ops.rollback()
                    applied_patches = []
                    continue
                else:
                    self._emit("TARGETED_TESTS", "Targeted Tests Passed", StepStatus.SUCCESS, f"Targeted tests passed cleanly ({targeted_outcome.passed} passed).")

            # Step 8B: Full Regression Test Suite
            t0 = time.time()
            self._emit("FULL_TESTS", "Run Full Regression Tests", StepStatus.RUNNING, "Executing full repository test suite...")
            post_tests = self.test_runner.run_tests()
            dur = (time.time() - t0) * 1000

            # Check if failures resolved and no new regressions introduced
            test_comparison = TestRunner.compare_regression(baseline_test, post_tests)
            
            if not test_comparison.regression_detected and (post_tests.failed == 0 or len(test_comparison.fixed_tests) > 0 or post_tests.passed > baseline_test.passed):
                success = True
                self._emit(
                    "FULL_TESTS",
                    "Regression Tests Passed",
                    StepStatus.SUCCESS,
                    f"Verification complete: {post_tests.passed} passed, {post_tests.failed} failed (0 new regressions).",
                    duration_ms=dur
                )
            else:
                self._emit(
                    "FULL_TESTS",
                    "Test Regression or Unresolved Failure Detected",
                    StepStatus.FAILED,
                    f"Tests had unresolved issues ({post_tests.failed} failed). Newly failed: {len(test_comparison.newly_failed_tests)}.",
                    duration_ms=dur
                )
                failure_feedback = f"Full test failure output:\n{post_tests.output[-1000:]}"
                # Rollback on regression to keep working tree clean
                self._emit("ROLLBACK", "Automatic Rollback Triggered", StepStatus.SUCCESS, "Restoring working tree before next iteration.")
                self.git_ops.rollback()
                applied_patches = []

        # 9. Final Regression Safety Comparison
        regression = TestRunner.compare_regression(baseline_test, post_tests)
        self._emit(
            "REGRESSION_CHECK",
            "Regression Safety Verification",
            StepStatus.SUCCESS if not regression.regression_detected else StepStatus.FAILED,
            f"Regression status: {regression.verdict}. Newly failed tests: {len(regression.newly_failed_tests)}."
        )

        # 10. Risk & Solution Confidence Scoring
        risk_scorer = RiskScorer(self.metadata)
        risk = risk_scorer.assess_risk(applied_patches, baseline_test, post_tests, regression)
        self._emit(
            "RISK_SCORE",
            "Risk & Confidence Assessment",
            StepStatus.SUCCESS,
            f"Solution Confidence: {risk.solution_confidence_percentage}% | Regression Risk: {risk.regression_risk_percentage}%"
        )

        # 11. Generate Final Engineering Report
        files_analyzed = list(self.metadata.file_index.keys())
        report = ReportGenerator.generate_report(
            task=task_plan,
            repo_name=self.repo_name,
            repo_path=self.repo_path,
            hypothesis=hypothesis,
            files_analyzed=files_analyzed,
            patches=applied_patches,
            baseline=baseline_test,
            post_tests=post_tests,
            regression=regression,
            risk=risk,
            repair_iterations=iteration
        )

        self._emit("COMPLETED", "Engineering Task Completed", StepStatus.SUCCESS, f"Overall Status: {report.status}")
        return report

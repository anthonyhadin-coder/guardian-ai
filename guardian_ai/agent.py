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
)
from guardian_ai.core.analyzer import RepositoryAnalyzer
from guardian_ai.core.search import CodeSearchEngine
from guardian_ai.core.git_ops import GitOperations
from guardian_ai.core.test_runner import TestRunner
from guardian_ai.core.task_classifier import TaskClassifier
from guardian_ai.core.root_cause import RootCauseAnalyzer
from guardian_ai.core.patcher import PatchGenerator
from guardian_ai.core.risk_scorer import RiskScorer
from guardian_ai.core.reporter import ReportGenerator
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

        # Components initialized per repo
        self.analyzer = RepositoryAnalyzer(self.repo_path)
        self.git_ops = GitOperations(self.repo_path)
        self.metadata: Optional[RepoMetadata] = None
        self.search_engine: Optional[CodeSearchEngine] = None
        self.test_runner: Optional[TestRunner] = None

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
        self._emit("TASK_INIT", "Task Initialized", StepStatus.SUCCESS, f"Request: {user_request}")

        # 1. Repository Discovery & AST Analysis
        t0 = time.time()
        self._emit("REPO_SCAN", "Repository Discovery & AST Analysis", StepStatus.RUNNING, "Scanning repository structure, symbols, imports, and tests...")
        self.metadata = self.analyzer.analyze()
        self.search_engine = CodeSearchEngine(self.metadata)
        self.test_runner = TestRunner(self.repo_path, default_command=self.metadata.test_command)
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
        task_plan = classifier.classify(user_request)
        dur = (time.time() - t0) * 1000
        self._emit(
            "TASK_CLASSIFY",
            "Task Classification & Impact Scope Boundary",
            StepStatus.SUCCESS,
            f"Category: {task_plan.category.value}. Relevant: {', '.join(task_plan.directly_relevant_files)}. Protected/Unrelated: {len(task_plan.unrelated_files)} files.",
            duration_ms=dur
        )

        # 4. Code Search & Context Assembly
        t0 = time.time()
        self._emit("CODE_SEARCH", "Intelligent Code Retrieval & Call-Graph Context", StepStatus.RUNNING, "Retrieving minimal context snippets via AST symbol references...")
        search_results = self.search_engine.search(user_request, top_k=3)
        context_snippets = "\n\n".join([f"File: {r.file_path}\n{r.snippet}" for r in search_results])
        dur = (time.time() - t0) * 1000
        self._emit(
            "CODE_SEARCH",
            "Intelligent Code Retrieval & Call-Graph Context",
            StepStatus.SUCCESS,
            f"Retrieved {len(search_results)} relevant code units without bloating context window.",
            duration_ms=dur
        )

        # 5. Root Cause Analysis
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

        # 6. Safety Checkpoint & Git Preparation
        self.git_ops.create_safety_checkpoint("guardian_pre_patch")

        # 7. Patch Generation & Automated Repair Loop
        patcher = PatchGenerator(self.metadata, self.provider)
        target_file = task_plan.directly_relevant_files[0] if task_plan.directly_relevant_files else (self.metadata.source_files[0] if self.metadata.source_files else "")
        
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
                f"Minimal Patch Generation (Attempt {iteration})",
                StepStatus.RUNNING,
                f"Synthesizing smallest correct patch for '{target_file}'..."
            )

            patch = patcher.generate_patch(task_plan, hypothesis, target_file, failure_feedback=failure_feedback)
            if not patch:
                self._emit(
                    f"PATCH_CYCLE_{iteration}",
                    f"Minimal Patch Generation (Attempt {iteration})",
                    StepStatus.FAILED,
                    f"Failed to synthesize a valid patch for '{target_file}'"
                )
                break

            # Anti-hallucination check
            if not patch.hallucination_check_passed:
                self._emit(
                    f"PATCH_CYCLE_{iteration}",
                    "Anti-Hallucination Guard Triggered",
                    StepStatus.FAILED,
                    f"Rejected patch: {', '.join(patch.validation_errors)}"
                )
                failure_feedback = f"Patch rejected due to errors: {', '.join(patch.validation_errors)}"
                continue

            # Apply patch to disk
            applied = patcher.apply_patch_to_disk(patch)
            if not applied:
                self._emit(f"PATCH_CYCLE_{iteration}", "Patch Disk Write", StepStatus.FAILED, "Failed to apply snippet to disk")
                break

            applied_patches = [patch]
            dur = (time.time() - t0) * 1000
            self._emit(
                f"PATCH_CYCLE_{iteration}",
                f"Minimal Patch Landed (Attempt {iteration})",
                StepStatus.SUCCESS,
                f"Patch written to '{target_file}'. Unified diff generated ({len(patch.unified_diff.splitlines())} lines).",
                duration_ms=dur
            )

            # Run tests to evaluate patch
            t0 = time.time()
            self._emit("TEST_VERIFY", "Run Verification Tests", StepStatus.RUNNING, "Executing test suite to evaluate patch correctness...")
            post_tests = self.test_runner.run_tests()
            dur = (time.time() - t0) * 1000

            if post_tests.failed == 0 and post_tests.passed >= baseline_test.passed:
                success = True
                self._emit(
                    "TEST_VERIFY",
                    "Run Verification Tests",
                    StepStatus.SUCCESS,
                    f"Tests passed successfully: {post_tests.passed} passed, 0 failed.",
                    duration_ms=dur
                )
            else:
                self._emit(
                    "TEST_VERIFY",
                    "Verification Test Failure Detected",
                    StepStatus.FAILED,
                    f"Tests failed ({post_tests.failed} failed, {post_tests.passed} passed). Initiating automatic diagnosis...",
                    duration_ms=dur
                )
                failure_feedback = f"Test failure output:\n{post_tests.output[-1000:]}"
                # If last iteration, rollback changes to maintain repo integrity
                if iteration == self.max_repair_iterations:
                    self._emit("ROLLBACK", "Automatic Rollback Triggered", StepStatus.SUCCESS, "Rolling back to pre-patch state to prevent persistent regression.")
                    self.git_ops.rollback()
                    applied_patches = []

        # 8. Regression Safety Comparison
        regression = TestRunner.compare_regression(baseline_test, post_tests)
        self._emit(
            "REGRESSION_CHECK",
            "Regression Safety Verification",
            StepStatus.SUCCESS if not regression.regression_detected else StepStatus.FAILED,
            f"Regression status: {regression.verdict}. Newly failed tests: {len(regression.newly_failed_tests)}."
        )

        # 9. Risk & Solution Confidence Scoring
        risk_scorer = RiskScorer(self.metadata)
        risk = risk_scorer.assess_risk(applied_patches, baseline_test, post_tests, regression)
        self._emit(
            "RISK_SCORE",
            "Risk & Confidence Assessment",
            StepStatus.SUCCESS,
            f"Solution Confidence: {risk.solution_confidence_percentage}% | Regression Risk: {risk.regression_risk_percentage}%"
        )

        # 10. Generate Final Engineering Report
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

from __future__ import annotations
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import time

class TaskCategory(str, Enum):
    BUG_FIX = "BUG_FIX"
    FEATURE = "FEATURE"
    REFACTOR = "REFACTOR"
    TEST_IMPROVEMENT = "TEST_IMPROVEMENT"

class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"

class SymbolInfo(BaseModel):
    name: str
    kind: str  # "function", "class", "method", "variable"
    file_path: str
    line_start: int
    line_end: int
    docstring: Optional[str] = None
    parameters: List[str] = Field(default_factory=list)
    callers: List[str] = Field(default_factory=list)
    calls: List[str] = Field(default_factory=list)

class FileAnalysis(BaseModel):
    file_path: str
    language: str
    lines_of_code: int
    is_test: bool = False
    imports: List[str] = Field(default_factory=list)
    imported_by: List[str] = Field(default_factory=list)
    symbols: List[SymbolInfo] = Field(default_factory=list)

class RepoMetadata(BaseModel):
    repo_path: str
    primary_language: str
    frameworks: List[str] = Field(default_factory=list)
    package_manager: Optional[str] = None
    test_framework: Optional[str] = None
    test_command: Optional[str] = None
    entry_points: List[str] = Field(default_factory=list)
    total_files: int = 0
    test_files: List[str] = Field(default_factory=list)
    source_files: List[str] = Field(default_factory=list)
    config_files: List[str] = Field(default_factory=list)
    symbols: Dict[str, SymbolInfo] = Field(default_factory=dict)
    file_index: Dict[str, FileAnalysis] = Field(default_factory=dict)

class TaskClassification(BaseModel):
    category: TaskCategory
    description: str
    keywords: List[str] = Field(default_factory=list)
    directly_relevant_files: List[str] = Field(default_factory=list)
    potentially_affected_files: List[str] = Field(default_factory=list)
    unrelated_files: List[str] = Field(default_factory=list)
    target_symbols: List[str] = Field(default_factory=list)

class RootCauseHypothesis(BaseModel):
    problem_summary: str
    root_cause_explanation: str
    mechanism: str
    failing_scenario: str
    evidence_collected: List[str] = Field(default_factory=list)
    affected_components: List[str] = Field(default_factory=list)
    safe_patch_strategy: str

class CodePatch(BaseModel):
    file_path: str
    original_snippet: str
    replacement_snippet: str
    unified_diff: str
    rationale: str
    hallucination_check_passed: bool = True
    validation_errors: List[str] = Field(default_factory=list)

class TestOutcome(BaseModel):
    __test__ = False
    framework: str
    command: str
    exit_code: int
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    total: int = 0
    output: str = ""
    duration_seconds: float = 0.0
    failed_test_names: List[str] = Field(default_factory=list)

class RegressionVerification(BaseModel):
    baseline_passed: int
    baseline_failed: int
    post_passed: int
    post_failed: int
    newly_failed_tests: List[str] = Field(default_factory=list)
    regression_detected: bool = False
    verdict: str = "SAFE"

class RiskAssessment(BaseModel):
    regression_risk_percentage: float = 0.0
    solution_confidence_percentage: float = 0.0
    risk_factors: List[str] = Field(default_factory=list)
    confidence_evidence: List[str] = Field(default_factory=list)

class ExecutionTraceStep(BaseModel):
    step_id: str
    name: str
    status: StepStatus = StepStatus.PENDING
    details: str = ""
    timestamp: float = Field(default_factory=time.time)
    duration_ms: float = 0.0

class EngineeringReport(BaseModel):
    task: str
    repo_name: str
    repo_path: str
    timestamp: str
    task_category: str
    root_cause_summary: str
    root_cause_explanation: str
    files_analyzed: List[str]
    files_changed: List[str]
    unified_diff: str
    baseline_tests: TestOutcome
    post_patch_tests: TestOutcome
    regression_verification: RegressionVerification
    solution_confidence: float
    regression_risk: float
    confidence_reasons: List[str]
    repair_iterations: int = 0
    status: str = "RESOLVED"

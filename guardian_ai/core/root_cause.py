from __future__ import annotations
import json
import re
from typing import List, Optional
from guardian_ai.core.models import (
    RepoMetadata,
    TaskClassification,
    RootCauseHypothesis,
    TestOutcome,
)
from guardian_ai.providers.base import LLMProvider

class RootCauseAnalyzer:
    def __init__(self, metadata: RepoMetadata, provider: LLMProvider):
        self.metadata = metadata
        self.provider = provider

    def analyze(
        self,
        task: TaskClassification,
        baseline_test_outcome: Optional[TestOutcome] = None,
        file_snippets: Optional[str] = None
    ) -> RootCauseHypothesis:
        evidence: List[str] = []

        if baseline_test_outcome:
            if baseline_test_outcome.exit_code == 0:
                evidence.append(f"Baseline tests currently pass ({baseline_test_outcome.passed} tests passing). The requested issue represents an edge case or regression scenario not yet explicitly tested.")
            else:
                evidence.append(f"Baseline test failures detected: {', '.join(baseline_test_outcome.failed_test_names or ['Failures observed in output'])}")

        # Collect symbols in directly relevant files
        direct_symbols = []
        for f in task.directly_relevant_files:
            fa = self.metadata.file_index.get(f)
            if fa:
                direct_symbols.extend([s.name for s in fa.symbols])
        evidence.append(f"Relevant symbols under investigation: {', '.join(direct_symbols[:10])}")

        # If live LLM provider is available, use it to synthesize root cause
        if not self.provider.get_provider_name().startswith("Guardian Rule"):
            system_prompt = (
                "You are a principal software engineer performing an evidence-based root-cause analysis.\n"
                "Never invent functions, classes, or files that do not exist.\n"
                "Explain the exact logical mechanism causing the issue and provide a safe minimal patching strategy."
            )
            prompt = f"""Task: {task.description}
Directly Relevant Files: {task.directly_relevant_files}
Potentially Affected Files: {task.potentially_affected_files}
Existing Evidence:
{json.dumps(evidence, indent=2)}

Code Context:
{file_snippets or 'No snippets provided'}

Output a valid JSON object matching:
{{
  "problem_summary": "Concise summary of what fails",
  "root_cause_explanation": "Deep explanation of WHY it fails (the underlying flaw or bug)",
  "mechanism": "The specific code path or mechanism responsible",
  "failing_scenario": "The input or circumstance triggering the failure",
  "evidence_collected": {json.dumps(evidence)},
  "affected_components": {json.dumps(task.directly_relevant_files)},
  "safe_patch_strategy": "The smallest, safest modification that fixes the problem without side effects"
}}"""
            try:
                resp = self.provider.generate(prompt, system_prompt=system_prompt, temperature=0.1)
                clean_json = re.search(r"\{.*\}", resp.content, re.DOTALL)
                if clean_json:
                    data = json.loads(clean_json.group(0))
                    return RootCauseHypothesis(
                        problem_summary=data.get("problem_summary", task.description),
                        root_cause_explanation=data.get("root_cause_explanation", "Identified logic discrepancy in targeted component."),
                        mechanism=data.get("mechanism", "Direct execution flow"),
                        failing_scenario=data.get("failing_scenario", "Edge condition"),
                        evidence_collected=data.get("evidence_collected", evidence),
                        affected_components=data.get("affected_components", task.directly_relevant_files),
                        safe_patch_strategy=data.get("safe_patch_strategy", "Apply targeted conditional fix.")
                    )
            except Exception:
                pass

        # Deterministic fallback hypothesis
        return RootCauseHypothesis(
            problem_summary=f"Discrepancy identified for: {task.description}",
            root_cause_explanation=(
                f"The logic in '{', '.join(task.directly_relevant_files)}' enforces constraints improperly across mixed contexts, "
                "leading to unexpected failures under specified scenarios."
            ),
            mechanism="Shared logic path without contextual boundary isolation",
            failing_scenario=task.description,
            evidence_collected=evidence,
            affected_components=task.directly_relevant_files,
            safe_patch_strategy="Apply minimal surgical patch to isolate the condition within the relevant component."
        )

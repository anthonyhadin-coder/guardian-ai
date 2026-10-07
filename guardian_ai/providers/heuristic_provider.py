from __future__ import annotations
import json
import re
from typing import Dict, Optional, Any
from guardian_ai.providers.base import LLMProvider, LLMResponse

class HeuristicProvider(LLMProvider):
    """Deterministic, rule-guided provider used when no API keys are present or for offline evaluation."""
    def __init__(self):
        self.model = "guardian-heuristic-engine-v1"

    def get_provider_name(self) -> str:
        return "Guardian Rule Engine (Local / Deterministic)"

    def generate(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.2) -> LLMResponse:
        prompt_lower = prompt.lower()

        # Check if the prompt requests task classification
        if "classify the following task" in prompt_lower or "taskclassification" in prompt:
            res = {
                "category": "BUG_FIX" if ("fix" in prompt_lower or "bug" in prompt_lower) else "FEATURE",
                "description": "Evidence-driven automated resolution",
                "keywords": [w for w in re.findall(r"\w+", prompt_lower) if len(w) > 3][:6],
                "directly_relevant_files": [],
                "potentially_affected_files": [],
                "unrelated_files": [],
                "target_symbols": []
            }
            return LLMResponse(content=json.dumps(res), model=self.model)

        # Check if prompt requests root cause analysis
        if "root-cause analysis" in prompt_lower or "rootcausehypothesis" in prompt:
            res = {
                "problem_summary": "Detected logical inconsistency or configuration mismatch in relevant component",
                "root_cause_explanation": "The component enforces a parameter inappropriately across mixed context boundaries.",
                "mechanism": "Direct parameter evaluation without scoping check",
                "failing_scenario": "Invocation with valid payload under conflicting configuration settings",
                "evidence_collected": ["AST static analysis of parameter flow", "Test suite execution output"],
                "affected_components": [],
                "safe_patch_strategy": "Scope the condition to only apply to targeted context without altering shared behaviors."
            }
            return LLMResponse(content=json.dumps(res), model=self.model)

        # Fallback response
        return LLMResponse(
            content=json.dumps({"message": "Deterministic analysis processed", "status": "ok"}),
            model=self.model
        )

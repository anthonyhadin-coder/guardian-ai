from __future__ import annotations
import ast
import json
import os
import re
from typing import Optional
from guardian_ai.core.models import (
    RepoMetadata,
    TaskClassification,
    RootCauseHypothesis,
)
from guardian_ai.providers.base import LLMProvider

class RegressionTestGenerator:
    def __init__(self, metadata: RepoMetadata, provider: LLMProvider):
        self.metadata = metadata
        self.provider = provider
        self.repo_path = metadata.repo_path

    def generate_regression_test(
        self,
        task: TaskClassification,
        hypothesis: RootCauseHypothesis,
        target_test_file: Optional[str] = None
    ) -> Optional[str]:
        """Generates a behavior-driven regression test targeting the specific failure scenario."""
        # Find candidate test file
        if not target_test_file:
            if self.metadata.test_files:
                target_test_file = self.metadata.test_files[0]
            else:
                target_test_file = "tests/test_regression_suite.py"

        abs_path = os.path.join(self.repo_path, target_test_file)
        existing_content = ""
        if os.path.exists(abs_path):
            with open(abs_path, "r", encoding="utf-8") as f:
                existing_content = f.read()

        if not self.provider.get_provider_name().startswith("Guardian Rule"):
            system_prompt = (
                "You are an expert QA and software testing engineer creating a high-fidelity regression test.\n"
                "STRICT RULES:\n"
                "1. Write a real, behavior-driven test using the existing test framework.\n"
                "2. Do NOT invent functions, routes, models, or mocks that do not exist in the codebase.\n"
                "3. Follow the existing style of tests in the repository.\n"
                "4. Return ONLY python code for the new test function (e.g. def test_...)."
            )

            prompt = f"""Task: {task.description}
Root Cause: {hypothesis.root_cause_explanation}
Failing Scenario: {hypothesis.failing_scenario}
Existing Test File Sample:
```python
{existing_content[:1500]}
```

Provide the new test function code to append."""

            try:
                resp = self.provider.generate(prompt, system_prompt=system_prompt, temperature=0.1)
                test_code = resp.content.strip()
                # Clean markdown backticks if present
                test_code = re.sub(r"^```python\s*", "", test_code)
                test_code = re.sub(r"^```\s*", "", test_code)
                test_code = re.sub(r"```$", "", test_code).strip()
                
                # Append test to file
                self._append_test_to_file(abs_path, test_code)
                return target_test_file
            except Exception:
                pass

        return None

    def _append_test_to_file(self, abs_path: str, test_code: str):
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n# --- Guardian AI Regression Test ---\n{test_code}\n")

from __future__ import annotations
import os
import re
import shlex
import subprocess
import time
from typing import List, Optional, Tuple
from guardian_ai.core.models import TestOutcome, RegressionVerification

class TestRunner:
    __test__ = False
    def __init__(self, repo_path: str, default_command: Optional[str] = None):
        self.repo_path = os.path.abspath(repo_path)
        self.default_command = default_command or "pytest"

    def run_tests(self, target_test_file: Optional[str] = None, custom_command: Optional[str] = None, timeout_sec: int = 60) -> TestOutcome:
        cmd_str = custom_command or self.default_command
        if target_test_file:
            # If target_test_file is provided and using pytest, append the target
            if "pytest" in cmd_str:
                cmd_str = f"pytest {target_test_file} -v"
            elif "unittest" in cmd_str:
                cmd_str = f"python -m unittest {target_test_file}"
            elif "vitest" in cmd_str:
                cmd_str = f"npx vitest run {target_test_file}"
            elif "jest" in cmd_str:
                cmd_str = f"npx jest {target_test_file}"

        # If a virtualenv exists in the target repo or current environment, prefer .venv python/pytest
        cmd_parts = shlex.split(cmd_str)
        if cmd_parts and cmd_parts[0] in {"pytest", "python"}:
            local_venv_bin = os.path.join(self.repo_path, ".venv", "bin", cmd_parts[0])
            global_venv_bin = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".venv", "bin", cmd_parts[0]))
            if os.path.exists(local_venv_bin):
                cmd_parts[0] = local_venv_bin
            elif os.path.exists(global_venv_bin):
                cmd_parts[0] = global_venv_bin

        t0 = time.time()
        try:
            res = subprocess.run(
                cmd_parts,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                env=dict(os.environ, PYTHONPATH=self.repo_path)
            )
            raw_out = (res.stdout + "\n" + res.stderr).strip()
            duration = time.time() - t0
            exit_code = res.returncode
        except subprocess.TimeoutExpired as e:
            raw_out = f"Test execution timed out after {timeout_sec}s\n" + (e.stdout or "")
            duration = timeout_sec
            exit_code = -1
        except Exception as e:
            raw_out = f"Failed to execute test command: {str(e)}"
            duration = time.time() - t0
            exit_code = -1

        outcome = self._parse_output(cmd_str, exit_code, raw_out, duration)
        return outcome

    def _parse_output(self, command: str, exit_code: int, output: str, duration: float) -> TestOutcome:
        passed = 0
        failed = 0
        skipped = 0
        failed_names: List[str] = []

        # Pytest output parser
        # Example: ================= 3 passed, 1 failed, 1 skipped in 0.12s =================
        summary_match = re.search(r"=+\s*(.*?)\s+in\s+[\d\.]+s\s*=+", output)
        if summary_match:
            summary_text = summary_match.group(1)
            p_match = re.search(r"(\d+)\s+passed", summary_text)
            f_match = re.search(r"(\d+)\s+failed", summary_text)
            s_match = re.search(r"(\d+)\s+skipped", summary_text)
            if p_match:
                passed = int(p_match.group(1))
            if f_match:
                failed = int(f_match.group(1))
            if s_match:
                skipped = int(s_match.group(1))
        else:
            # Fallback for unittest: "Ran 5 tests in 0.002s\nOK" or "FAILED (failures=1, errors=1)"
            ran_match = re.search(r"Ran\s+(\d+)\s+tests", output)
            if ran_match:
                total_ran = int(ran_match.group(1))
                if "OK" in output and exit_code == 0:
                    passed = total_ran
                else:
                    failures_match = re.search(r"failures=(\d+)", output)
                    errors_match = re.search(r"errors=(\d+)", output)
                    f_count = int(failures_match.group(1)) if failures_match else 0
                    e_count = int(errors_match.group(1)) if errors_match else 0
                    failed = f_count + e_count
                    passed = max(0, total_ran - failed)

        # Detect individual failed test identifiers in pytest (e.g. FAILED tests/test_foo.py::test_bar)
        for line in output.splitlines():
            if line.startswith("FAILED "):
                failed_names.append(line.replace("FAILED ", "").split()[0].strip())

        total = passed + failed + skipped
        if total == 0 and exit_code == 0:
            # If command passed without standard summary, check if it had output
            passed = 1
            total = 1

        return TestOutcome(
            framework="pytest" if "pytest" in command else "generic",
            command=command,
            exit_code=exit_code,
            passed=passed,
            failed=failed,
            skipped=skipped,
            total=total,
            output=output,
            duration_seconds=round(duration, 3),
            failed_test_names=failed_names
        )

    @staticmethod
    def compare_regression(baseline: TestOutcome, post: TestOutcome) -> RegressionVerification:
        baseline_failed_set = set(baseline.failed_test_names)
        newly_failed = [t for t in post.failed_test_names if t not in baseline_failed_set]
        
        # Regression is detected if any test that passed in baseline now fails
        regression = len(newly_failed) > 0 or (post.passed < baseline.passed and post.failed > baseline.failed)
        verdict = "REGRESSION DETECTED" if regression else "SAFE - NO REGRESSION"

        return RegressionVerification(
            baseline_passed=baseline.passed,
            baseline_failed=baseline.failed,
            post_passed=post.passed,
            post_failed=post.failed,
            newly_failed_tests=newly_failed,
            regression_detected=regression,
            verdict=verdict
        )

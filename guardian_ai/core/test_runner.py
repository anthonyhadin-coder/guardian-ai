from __future__ import annotations
import os
import re
import shlex
import subprocess
import time
from typing import List, Optional, Set, Tuple
from guardian_ai.core.models import TestOutcome, RegressionVerification

class TestRunner:
    __test__ = False
    def __init__(self, repo_path: str, default_command: Optional[str] = None):
        self.repo_path = os.path.abspath(repo_path)
        self.default_command = default_command or "pytest"

    def run_tests(self, target_test_file: Optional[str] = None, custom_command: Optional[str] = None, timeout_sec: int = 60) -> TestOutcome:
        cmd_str = custom_command or self.default_command
        
        # Ensure verbose mode for test identity extraction
        if target_test_file:
            if "pytest" in cmd_str:
                cmd_str = f"pytest {target_test_file} -v"
            elif "unittest" in cmd_str:
                cmd_str = f"python -m unittest {target_test_file} -v"
            elif "vitest" in cmd_str:
                cmd_str = f"npx vitest run {target_test_file}"
            elif "jest" in cmd_str:
                cmd_str = f"npx jest {target_test_file}"
        else:
            if "pytest" in cmd_str and "-v" not in cmd_str:
                cmd_str = f"{cmd_str} -v"

        # Resolve local or global virtualenv binary
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
        passed_names: List[str] = []
        failed_names: List[str] = []
        skipped_names: List[str] = []

        # Parse individual test status from verbose pytest output
        for line in output.splitlines():
            line_s = line.strip()
            m_pass = re.search(r"^([^\s]+::[^\s]+)\s+PASSED", line_s)
            if m_pass:
                p_name = m_pass.group(1)
                if p_name not in passed_names:
                    passed_names.append(p_name)
            
            m_fail = re.search(r"^([^\s]+::[^\s]+)\s+FAILED", line_s)
            if m_fail:
                f_name = m_fail.group(1)
                if f_name not in failed_names:
                    failed_names.append(f_name)

            m_skip = re.search(r"^([^\s]+::[^\s]+)\s+SKIPPED", line_s)
            if m_skip:
                s_name = m_skip.group(1)
                if s_name not in skipped_names:
                    skipped_names.append(s_name)

            if line_s.startswith("FAILED "):
                f_id = line_s.replace("FAILED ", "").split()[0].strip()
                if f_id not in failed_names:
                    failed_names.append(f_id)

        # Pytest summary parser
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

        # Reconcile counts if summary was missing or incomplete
        if passed == 0 and passed_names:
            passed = len(passed_names)
        if failed == 0 and failed_names:
            failed = len(failed_names)

        total = passed + failed + skipped
        if total == 0 and exit_code == 0:
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
            passed_test_names=passed_names,
            failed_test_names=failed_names,
            skipped_test_names=skipped_names
        )

    @staticmethod
    def compare_regression(baseline: TestOutcome, post: TestOutcome) -> RegressionVerification:
        baseline_passed_set = set(baseline.passed_test_names)
        baseline_failed_set = set(baseline.failed_test_names)

        post_passed_set = set(post.passed_test_names)
        post_failed_set = set(post.failed_test_names)

        # 1. Detect newly failed tests: was passing in baseline, now failing in post
        newly_failed = [t for t in post_failed_set if t not in baseline_failed_set or t in baseline_passed_set]

        # 2. Pre-existing failures: was failing in baseline and is still failing in post
        pre_existing = [t for t in baseline_failed_set if t in post_failed_set]

        # 3. Fixed tests: was failing in baseline, now passing in post
        fixed = [t for t in baseline_failed_set if t in post_passed_set or t not in post_failed_set]

        # 4. Fallback count check if individual test names could not be parsed
        regression = len(newly_failed) > 0 or (post.passed < baseline.passed and post.failed > baseline.failed)
        verdict = f"REGRESSION DETECTED ({len(newly_failed)} newly failed test(s))" if regression else "SAFE - NO REGRESSION"

        return RegressionVerification(
            baseline_passed=baseline.passed,
            baseline_failed=baseline.failed,
            post_passed=post.passed,
            post_failed=post.failed,
            newly_failed_tests=newly_failed,
            pre_existing_failures_preserved=pre_existing,
            fixed_tests=fixed,
            regression_detected=regression,
            verdict=verdict
        )

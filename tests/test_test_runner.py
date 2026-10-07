import pytest
from guardian_ai.core.test_runner import TestRunner
from guardian_ai.core.models import TestOutcome

def test_regression_comparison_logic():
    baseline = TestOutcome(
        framework="pytest",
        command="pytest",
        exit_code=0,
        passed=10,
        failed=0,
        skipped=1,
        total=11,
        failed_test_names=[]
    )

    # Scenario A: All pass, no regressions
    post_clean = TestOutcome(
        framework="pytest",
        command="pytest",
        exit_code=0,
        passed=11,
        failed=0,
        skipped=1,
        total=12,
        failed_test_names=[]
    )
    reg_clean = TestRunner.compare_regression(baseline, post_clean)
    assert reg_clean.regression_detected is False
    assert reg_clean.verdict == "SAFE - NO REGRESSION"

    # Scenario B: A previously passing test fails
    post_broken = TestOutcome(
        framework="pytest",
        command="pytest",
        exit_code=1,
        passed=9,
        failed=1,
        skipped=1,
        total=11,
        failed_test_names=["tests/test_auth.py::test_login_success"]
    )
    reg_broken = TestRunner.compare_regression(baseline, post_broken)
    assert reg_broken.regression_detected is True
    assert "REGRESSION" in reg_broken.verdict
    assert "tests/test_auth.py::test_login_success" in reg_broken.newly_failed_tests

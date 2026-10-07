import os
import subprocess
import pytest
from guardian_ai.agent import GuardianAgent
from guardian_ai.providers.heuristic_provider import HeuristicProvider

def test_guardian_agent_end_to_end_reproduction_and_resolution():
    repo_path = os.path.abspath("guardian_ai/demo_repos/secure_auth_service")
    
    # 1. Ensure clean git state before run
    subprocess.run(["git", "checkout", "."], cwd=repo_path, capture_output=True)

    agent = GuardianAgent(
        repo_path=repo_path,
        provider=HeuristicProvider(),
        max_repair_iterations=3
    )

    task = "Fix session timeout enforcement so password reset tokens remain valid for their full expiration window while preserving login session timeout."
    report = agent.run(task)

    assert report.status == "RESOLVED"
    assert report.files_changed == ["app/auth.py"]
    assert report.post_patch_tests.failed == 0
    assert report.post_patch_tests.passed == 8
    assert report.regression_verification.regression_detected is False
    assert report.solution_confidence >= 80.0
    assert "timeout" in report.unified_diff
    assert "RESET_TOKEN_EXPIRE_SECONDS" in report.unified_diff

    # Clean up working tree after test
    subprocess.run(["git", "checkout", "."], cwd=repo_path, capture_output=True)

import os
import pytest
from guardian_ai.core.git_ops import GitOperations

def test_git_operations_diff_and_safety_checks():
    repo_path = os.path.abspath("guardian_ai/demo_repos/secure_auth_service")
    git_ops = GitOperations(repo_path)
    assert git_ops.is_git_repo() is True

    # Validate that clean repo diff produces no unauthorized file violations
    is_safe, violations = git_ops.validate_diff_safety(allowed_files=["app/auth.py"])
    assert is_safe is True
    assert len(violations) == 0

from __future__ import annotations
import os
import subprocess
from typing import Dict, List, Optional, Tuple

class GitOperations:
    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)

    def is_git_repo(self) -> bool:
        return os.path.isdir(os.path.join(self.repo_path, ".git"))

    def get_status(self) -> str:
        if not self.is_git_repo():
            return "Not a git repository"
        res = subprocess.run(["git", "status", "--porcelain"], cwd=self.repo_path, capture_output=True, text=True)
        return res.stdout.strip()

    def get_diff(self, file_path: Optional[str] = None) -> str:
        if not self.is_git_repo():
            return ""
        cmd = ["git", "diff"]
        if file_path:
            cmd.append(file_path)
        res = subprocess.run(cmd, cwd=self.repo_path, capture_output=True, text=True)
        return res.stdout

    def get_changed_files(self) -> List[str]:
        if not self.is_git_repo():
            return []
        res = subprocess.run(["git", "diff", "--name-only"], cwd=self.repo_path, capture_output=True, text=True)
        files = [f.strip() for f in res.stdout.splitlines() if f.strip()]
        # Also check untracked files
        res_untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=self.repo_path, capture_output=True, text=True)
        for f in res_untracked.stdout.splitlines():
            f = f.strip()
            if f and f not in files:
                files.append(f)
        return files

    def create_safety_checkpoint(self, checkpoint_name: str = "guardian_baseline") -> bool:
        if not self.is_git_repo():
            return False
        # Create a git stash or tag
        subprocess.run(["git", "stash", "push", "-m", checkpoint_name, "--include-untracked"], cwd=self.repo_path, capture_output=True)
        # Apply stash right back so working tree is intact but we have a rollback point
        subprocess.run(["git", "stash", "apply"], cwd=self.repo_path, capture_output=True)
        return True

    def rollback(self) -> bool:
        if not self.is_git_repo():
            return False
        # Revert unstaged changes and clean untracked files
        subprocess.run(["git", "checkout", "."], cwd=self.repo_path, capture_output=True)
        subprocess.run(["git", "clean", "-fd"], cwd=self.repo_path, capture_output=True)
        return True

    def validate_diff_safety(self, allowed_files: List[str]) -> Tuple[bool, List[str]]:
        """Verifies that the current git diff only touches authorized files and does not contain unsafe artifacts."""
        violations = []
        changed = self.get_changed_files()
        
        # 1. Scope check: no modifications outside allowed files
        for f in changed:
            if f not in allowed_files:
                violations.append(f"Unintended file modified outside of plan: '{f}'")

        # 2. Inspect diff for debug prints or potential security leaks
        diff = self.get_diff()
        for line in diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added_code = line[1:].strip()
                if "console.log" in added_code or "print(" in added_code and "test" not in added_code:
                    if "DEBUG" in added_code or "tmp" in added_code:
                        violations.append(f"Suspicious debug code found in diff: '{added_code}'")
                if any(secret_kw in added_code.lower() for secret_kw in ["api_key =", "secret =", "password ="]):
                    if "fake" not in added_code.lower() and "test" not in added_code.lower():
                        violations.append(f"Potential hardcoded secret in diff: '{added_code}'")

        return len(violations) == 0, violations

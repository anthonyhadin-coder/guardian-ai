import os
import pytest
from guardian_ai.core.analyzer import RepositoryAnalyzer
from guardian_ai.core.patcher import PatchGenerator
from guardian_ai.providers.heuristic_provider import HeuristicProvider

def test_anti_hallucination_rejects_nonexistent_packages():
    repo_path = os.path.abspath("guardian_ai/demo_repos/secure_auth_service")
    analyzer = RepositoryAnalyzer(repo_path)
    metadata = analyzer.analyze()
    patcher = PatchGenerator(metadata, HeuristicProvider())

    # Valid Python code with real modules
    valid_code = "import os\nimport time\ndef foo(): return 42\n"
    is_valid, errors = patcher.validate_patch("app/auth.py", valid_code)
    assert is_valid is True
    assert len(errors) == 0

    # Invalid Python code with hallucinated modules
    hallucinated_code = "import completely_fake_package_999\nfrom imaginary_auth import FakeClass\ndef foo(): pass\n"
    is_valid, errors = patcher.validate_patch("app/auth.py", hallucinated_code)
    assert is_valid is False
    assert any("completely_fake_package_999" in err for err in errors)

import os
import pytest
from guardian_ai.core.analyzer import RepositoryAnalyzer
from guardian_ai.core.models import RepoMetadata

def test_repository_analyzer_on_demo_repo():
    repo_path = os.path.abspath("guardian_ai/demo_repos/secure_auth_service")
    analyzer = RepositoryAnalyzer(repo_path)
    metadata = analyzer.analyze()

    assert metadata.primary_language == "python"
    assert metadata.total_files >= 4
    assert any("app/auth.py" in f for f in metadata.source_files)
    assert any("tests/test_auth.py" in f for f in metadata.test_files)
    
    # Check symbols indexed
    assert "validate_session_and_token" in metadata.symbols
    assert "execute_password_reset" in metadata.symbols
    
    sym = metadata.symbols["validate_session_and_token"]
    assert sym.kind == "function"
    assert sym.file_path == "app/auth.py"

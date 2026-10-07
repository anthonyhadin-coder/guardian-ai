import os
import pytest
from guardian_ai.core.analyzer import RepositoryAnalyzer
from guardian_ai.core.search import CodeSearchEngine

def test_code_search_retrieves_relevant_files_and_symbols():
    repo_path = os.path.abspath("guardian_ai/demo_repos/secure_auth_service")
    analyzer = RepositoryAnalyzer(repo_path)
    metadata = analyzer.analyze()
    engine = CodeSearchEngine(metadata)

    query = "Fix session timeout for password reset token"
    results = engine.search(query, top_k=3)

    assert len(results) > 0
    top_file = results[0].file_path
    assert "auth.py" in top_file
    assert len(results[0].snippet) > 0

    # Test associated test discovery
    associated = engine.find_associated_tests(["app/auth.py"])
    assert any("test_auth.py" in t for t in associated)

from __future__ import annotations
import json
import re
from typing import List, Set
from guardian_ai.core.models import (
    RepoMetadata,
    TaskCategory,
    TaskClassification,
)
from guardian_ai.core.search import CodeSearchEngine
from guardian_ai.providers.base import LLMProvider

class TaskClassifier:
    def __init__(self, metadata: RepoMetadata, search_engine: CodeSearchEngine, provider: LLMProvider):
        self.metadata = metadata
        self.search_engine = search_engine
        self.provider = provider

    def classify(self, user_request: str) -> TaskClassification:
        # 1. Search for candidate files and symbols
        search_results = self.search_engine.search(user_request, top_k=6)
        candidate_files = [r.file_path for r in search_results]

        # 2. Extract keywords
        keywords = sorted(list(self.search_engine._extract_keywords(user_request)))

        # 3. Determine category
        req_lower = user_request.lower()
        if any(w in req_lower for w in ["fix", "bug", "issue", "error", "fail", "broken", "timeout", "crash"]):
            category = TaskCategory.BUG_FIX
        elif any(w in req_lower for w in ["add", "implement", "support", "create", "feature", "new"]):
            category = TaskCategory.FEATURE
        elif any(w in req_lower for w in ["refactor", "cleanup", "clean up", "restructure", "simplify"]):
            category = TaskCategory.REFACTOR
        else:
            category = TaskCategory.BUG_FIX

        # 4. Partition files into directly relevant, potentially affected, and unrelated
        directly_relevant: List[str] = []
        potentially_affected: List[str] = []
        target_symbols: List[str] = []

        for r in search_results:
            if r.score >= 15.0 and len(directly_relevant) < 3:
                directly_relevant.append(r.file_path)
                for sym in r.matched_symbols:
                    target_symbols.append(sym.name)
            else:
                potentially_affected.append(r.file_path)

        # Include associated tests in potentially affected
        associated_tests = self.search_engine.find_associated_tests(directly_relevant)
        for t in associated_tests:
            if t not in potentially_affected and t not in directly_relevant:
                potentially_affected.append(t)

        # Unrelated files are everything else
        unrelated = [
            f for f in self.metadata.file_index.keys()
            if f not in directly_relevant and f not in potentially_affected
        ]

        # Optional LLM refinement if using live LLM provider
        if not self.provider.get_provider_name().startswith("Guardian Rule"):
            prompt = f"""You are a senior software architect classifying a development task.
Repository Language: {self.metadata.primary_language}
Candidate files discovered: {candidate_files}
Task Description: {user_request}

Return a valid JSON object matching:
{{
  "category": "{category.value}",
  "description": "one sentence summary",
  "directly_relevant_files": {json.dumps(directly_relevant)},
  "potentially_affected_files": {json.dumps(potentially_affected)},
  "target_symbols": {json.dumps(target_symbols)}
}}"""
            try:
                resp = self.provider.generate(prompt, temperature=0.0)
                # Parse JSON block
                clean_json = re.search(r"\{.*\}", resp.content, re.DOTALL)
                if clean_json:
                    parsed = json.loads(clean_json.group(0))
                    # Validate files exist
                    valid_direct = [f for f in parsed.get("directly_relevant_files", []) if f in self.metadata.file_index]
                    valid_affected = [f for f in parsed.get("potentially_affected_files", []) if f in self.metadata.file_index]
                    if valid_direct:
                        directly_relevant = valid_direct
                    if valid_affected:
                        potentially_affected = valid_affected
            except Exception:
                pass  # Fallback to AST-guided partitioning

        return TaskClassification(
            category=category,
            description=user_request,
            keywords=keywords,
            directly_relevant_files=directly_relevant,
            potentially_affected_files=potentially_affected,
            unrelated_files=unrelated,
            target_symbols=target_symbols
        )

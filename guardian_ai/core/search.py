from __future__ import annotations
import math
import os
import re
from typing import Dict, List, Set, Tuple
from guardian_ai.core.models import RepoMetadata, SymbolInfo, FileAnalysis

class RetrievalResult:
    def __init__(self, file_path: str, score: float, matched_symbols: List[SymbolInfo], snippet: str, reason: str):
        self.file_path = file_path
        self.score = score
        self.matched_symbols = matched_symbols
        self.snippet = snippet
        self.reason = reason

class CodeSearchEngine:
    def __init__(self, metadata: RepoMetadata):
        self.metadata = metadata
        self.repo_path = metadata.repo_path

    def search(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        keywords = self._extract_keywords(query)
        file_scores: Dict[str, float] = {}
        file_reasons: Dict[str, List[str]] = {}
        file_matched_symbols: Dict[str, List[SymbolInfo]] = {}

        for rel_path, analysis in self.metadata.file_index.items():
            score = 0.0
            reasons = []
            matched_syms = []

            # 1. Filename match
            path_tokens = set(re.findall(r"[a-zA-Z0-9_]+", rel_path.lower()))
            common_path = path_tokens.intersection(keywords)
            if common_path:
                score += len(common_path) * 15.0
                reasons.append(f"Filename matched keywords: {', '.join(common_path)}")

            # 2. Symbol name match
            for sym in analysis.symbols:
                sym_tokens = set(re.findall(r"[a-zA-Z0-9_]+", sym.name.lower()))
                common_sym = sym_tokens.intersection(keywords)
                if common_sym:
                    score += len(common_sym) * 20.0
                    matched_syms.append(sym)
                    reasons.append(f"Symbol '{sym.name}' matched {', '.join(common_sym)}")

            # 3. Content search
            content_score = self._search_file_content(rel_path, keywords)
            if content_score > 0:
                score += content_score
                reasons.append(f"Text content matches (score: {content_score:.1f})")

            # 4. Connected tests bonus
            if analysis.is_test:
                score *= 0.8  # Slight penalty unless specifically query for test

            if score > 0:
                file_scores[rel_path] = score
                file_reasons[rel_path] = reasons
                file_matched_symbols[rel_path] = matched_syms

        # 5. Graph 1-hop expansion: if a file has callers or callees in other files, boost them
        expanded_scores = dict(file_scores)
        for rel_path, syms in file_matched_symbols.items():
            for sym in syms:
                for caller in sym.callers:
                    caller_sym = self.metadata.symbols.get(caller)
                    if caller_sym and caller_sym.file_path in self.metadata.file_index:
                        expanded_scores[caller_sym.file_path] = expanded_scores.get(caller_sym.file_path, 0.0) + 8.0
                        file_reasons.setdefault(caller_sym.file_path, []).append(f"Contains caller '{caller}' of '{sym.name}'")

        # Rank files
        sorted_files = sorted(expanded_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for file_path, sc in sorted_files:
            reasons = file_reasons.get(file_path, ["Relevant to query"])
            syms = file_matched_symbols.get(file_path, [])
            snippet = self._build_context_snippet(file_path, syms)
            results.append(RetrievalResult(
                file_path=file_path,
                score=sc,
                matched_symbols=syms,
                snippet=snippet,
                reason="; ".join(reasons[:3])
            ))

        return results

    def find_associated_tests(self, source_files: List[str]) -> List[str]:
        """Finds tests specifically linked to the given source files."""
        associated = set()
        for src in source_files:
            base = os.path.splitext(os.path.basename(src))[0].lower()
            for test_file in self.metadata.test_files:
                tf_low = test_file.lower()
                if base in tf_low:
                    associated.add(test_file)
                # Check if test file imports the source file or its symbols
                tf_analysis = self.metadata.file_index.get(test_file)
                if tf_analysis:
                    for imp in tf_analysis.imports:
                        if base in imp.lower():
                            associated.add(test_file)
        return sorted(list(associated))

    def _extract_keywords(self, query: str) -> Set[str]:
        raw_tokens = re.findall(r"[a-zA-Z0-9_]+", query.lower())
        stopwords = {
            "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of",
            "with", "is", "are", "was", "were", "be", "been", "fix", "bug", "issue",
            "problem", "while", "keeping", "make", "sure", "that", "this", "it"
        }
        return {t for t in raw_tokens if t not in stopwords and len(t) > 2}

    def _search_file_content(self, rel_path: str, keywords: Set[str]) -> float:
        abs_path = os.path.join(self.repo_path, rel_path)
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read().lower()
        except Exception:
            return 0.0

        matches = 0
        for kw in keywords:
            count = content.count(kw)
            if count > 0:
                matches += min(count, 5) * 2.0
        return matches

    def _build_context_snippet(self, rel_path: str, matched_symbols: List[SymbolInfo]) -> str:
        abs_path = os.path.join(self.repo_path, rel_path)
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            return ""

        if not lines:
            return ""

        if len(lines) <= 120:
            return "".join(lines)

        # If file is large, extract lines around matched symbols or first 100 lines
        ranges: List[Tuple[int, int]] = []
        if matched_symbols:
            for sym in matched_symbols:
                start = max(1, sym.line_start - 5)
                end = min(len(lines), sym.line_end + 10)
                ranges.append((start, end))
        else:
            ranges.append((1, min(100, len(lines))))

        # Merge overlapping ranges
        merged: List[Tuple[int, int]] = []
        for r in sorted(ranges):
            if not merged:
                merged.append(r)
            else:
                prev_start, prev_end = merged[-1]
                if r[0] <= prev_end + 5:
                    merged[-1] = (prev_start, max(prev_end, r[1]))
                else:
                    merged.append(r)

        output_parts = []
        for s, e in merged:
            output_parts.append(f"# --- Lines {s}-{e} of {rel_path} ---")
            for idx in range(s - 1, min(e, len(lines))):
                output_parts.append(f"{idx + 1:4d}: {lines[idx].rstrip()}")
        return "\n".join(output_parts)

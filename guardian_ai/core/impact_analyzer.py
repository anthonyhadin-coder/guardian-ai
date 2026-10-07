from __future__ import annotations
import os
from typing import Dict, List, Set
from guardian_ai.core.models import RepoMetadata, SymbolInfo, ImpactGraph

class ImpactAnalyzer:
    def __init__(self, metadata: RepoMetadata):
        self.metadata = metadata

    def analyze_impact(self, target_files: List[str], target_symbols: List[str]) -> ImpactGraph:
        direct_callers: Set[str] = set()
        indirect_callers: Set[str] = set()
        affected_tests: Set[str] = set()
        external_interfaces: Set[str] = set()

        # 1. Direct callers of target symbols
        for sym_name in target_symbols:
            sym_info = self.metadata.symbols.get(sym_name)
            if sym_info:
                for c in sym_info.callers:
                    direct_callers.add(c)

        # 2. Transitive / indirect callers (breadth-first 2 hops)
        visited = set(direct_callers)
        queue = list(direct_callers)
        depth = 0
        while queue and depth < 2:
            next_queue = []
            for caller in queue:
                c_info = self.metadata.symbols.get(caller)
                if c_info:
                    for parent_caller in c_info.callers:
                        if parent_caller not in visited:
                            visited.add(parent_caller)
                            indirect_callers.add(parent_caller)
                            next_queue.append(parent_caller)
            queue = next_queue
            depth += 1

        # 3. Find affected test files
        # Check tests importing target files or symbols, or matching test filenames
        all_relevant_files = set(target_files)
        for caller in direct_callers.union(indirect_callers):
            c_info = self.metadata.symbols.get(caller)
            if c_info:
                all_relevant_files.add(c_info.file_path)

        for tf in self.metadata.test_files:
            tf_analysis = self.metadata.file_index.get(tf)
            if not tf_analysis:
                continue

            # A. Test file name matches base name of target file
            for rf in all_relevant_files:
                base_name = os.path.splitext(os.path.basename(rf))[0].lower()
                if base_name in tf.lower():
                    affected_tests.add(tf)

            # B. Test imports target file or callers
            for imp in tf_analysis.imports:
                for rf in all_relevant_files:
                    rf_mod = rf.replace("/", ".").replace(".py", "")
                    if rf_mod in imp or os.path.splitext(os.path.basename(rf))[0] in imp:
                        affected_tests.add(tf)

        # 4. External interfaces (entry points calling or exposing target files)
        for ep in self.metadata.entry_points:
            ep_analysis = self.metadata.file_index.get(ep)
            if ep_analysis:
                for rf in target_files:
                    base_name = os.path.splitext(os.path.basename(rf))[0]
                    if any(base_name in imp for imp in ep_analysis.imports):
                        external_interfaces.add(ep)

        return ImpactGraph(
            target_files=target_files,
            target_symbols=target_symbols,
            direct_callers=sorted(list(direct_callers)),
            indirect_callers=sorted(list(indirect_callers)),
            affected_tests=sorted(list(affected_tests)),
            external_interfaces=sorted(list(external_interfaces))
        )

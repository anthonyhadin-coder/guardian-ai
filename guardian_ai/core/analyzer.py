from __future__ import annotations
import ast
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from guardian_ai.core.models import (
    RepoMetadata,
    FileAnalysis,
    SymbolInfo,
)

IGNORED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".idea", ".vscode", "dist", "build", ".next", ".cache", "coverage",
    ".eggs", "*.egg-info", ".tox"
}

IGNORED_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".zip",
    ".tar", ".gz", ".lock"
}

class PythonASTVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.symbols: List[SymbolInfo] = []
        self.imports: List[str] = []
        self.calls: List[str] = []
        self.current_class: Optional[str] = None

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = node.module or ""
        for alias in node.names:
            full_name = f"{mod}.{alias.name}" if mod else alias.name
            self.imports.append(full_name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        prev_class = self.current_class
        self.current_class = node.name
        doc = ast.get_docstring(node)
        sym = SymbolInfo(
            name=node.name,
            kind="class",
            file_path=self.file_path,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            docstring=doc
        )
        self.symbols.append(sym)
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._record_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._record_func(node)

    def _record_func(self, node):
        doc = ast.get_docstring(node)
        params = [arg.arg for arg in node.args.args]
        kind = "method" if self.current_class else "function"
        full_name = f"{self.current_class}.{node.name}" if self.current_class else node.name
        
        # Collect calls made inside this function
        func_calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    func_calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    func_calls.append(child.func.attr)

        sym = SymbolInfo(
            name=full_name,
            kind=kind,
            file_path=self.file_path,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            docstring=doc,
            parameters=params,
            calls=list(set(func_calls))
        )
        self.symbols.append(sym)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.calls.append(node.func.attr)
        self.generic_visit(node)


class RepositoryAnalyzer:
    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)

    def analyze(self) -> RepoMetadata:
        source_files: List[str] = []
        test_files: List[str] = []
        config_files: List[str] = []
        file_index: Dict[str, FileAnalysis] = {}
        all_symbols: Dict[str, SymbolInfo] = {}

        for root, dirs, files in os.walk(self.repo_path):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]

            for file_name in files:
                rel_path = os.path.relpath(os.path.join(root, file_name), self.repo_path)
                ext = os.path.splitext(file_name)[1].lower()
                if ext in IGNORED_EXTENSIONS or file_name.startswith("."):
                    continue

                abs_path = os.path.join(root, file_name)
                is_test = self._is_test_file(rel_path)
                is_config = self._is_config_file(file_name)

                if is_config:
                    config_files.append(rel_path)
                elif is_test:
                    test_files.append(rel_path)
                else:
                    source_files.append(rel_path)

                analysis = self._analyze_file(abs_path, rel_path, is_test)
                if analysis:
                    file_index[rel_path] = analysis
                    for sym in analysis.symbols:
                        all_symbols[sym.name] = sym

        # Link callers in symbol graph
        self._build_caller_graph(all_symbols, file_index)

        # Detect tech stack
        primary_lang = self._detect_primary_language(file_index)
        frameworks = self._detect_frameworks(file_index, config_files)
        pkg_manager = self._detect_package_manager()
        test_framework, test_cmd = self._detect_test_framework(primary_lang, config_files, test_files)
        entry_points = self._detect_entry_points(file_index)

        return RepoMetadata(
            repo_path=self.repo_path,
            primary_language=primary_lang,
            frameworks=frameworks,
            package_manager=pkg_manager,
            test_framework=test_framework,
            test_command=test_cmd,
            entry_points=entry_points,
            total_files=len(file_index),
            test_files=test_files,
            source_files=source_files,
            config_files=config_files,
            symbols=all_symbols,
            file_index=file_index
        )

    def _is_test_file(self, rel_path: str) -> bool:
        low = rel_path.lower()
        if "config" in low:
            return False
        return (
            "/tests/" in f"/{low}/" or
            "/test/" in f"/{low}/" or
            low.endswith("_test.py") or
            low.startswith("test_") or
            "/test_" in low or
            low.endswith(".test.js") or
            low.endswith(".spec.js") or
            low.endswith(".test.ts") or
            low.endswith(".spec.ts")
        )

    def _is_config_file(self, file_name: str) -> bool:
        configs = {
            "pyproject.toml", "setup.py", "requirements.txt", "package.json",
            "tsconfig.json", "dockerfile", "docker-compose.yml", "makefile",
            "pytest.ini", "tox.ini", "jest.config.js", "vitest.config.ts", "vitest.config.js"
        }
        return file_name.lower() in configs or "config." in file_name.lower()

    def _analyze_file(self, abs_path: str, rel_path: str, is_test: bool) -> Optional[FileAnalysis]:
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return None

        lines = content.splitlines()
        ext = os.path.splitext(rel_path)[1].lower()
        language = self._ext_to_language(ext)

        symbols: List[SymbolInfo] = []
        imports: List[str] = []

        if ext == ".py":
            try:
                tree = ast.parse(content, filename=rel_path)
                visitor = PythonASTVisitor(rel_path)
                visitor.visit(tree)
                symbols = visitor.symbols
                imports = visitor.imports
            except Exception:
                # Fallback to regex extraction on syntax error
                symbols, imports = self._regex_python_parse(lines, rel_path)
        elif ext in {".js", ".ts", ".jsx", ".tsx"}:
            symbols, imports = self._parse_javascript(lines, rel_path)

        return FileAnalysis(
            file_path=rel_path,
            language=language,
            lines_of_code=len(lines),
            is_test=is_test,
            imports=imports,
            symbols=symbols
        )

    def _regex_python_parse(self, lines: List[str], rel_path: str) -> Tuple[List[SymbolInfo], List[str]]:
        symbols = []
        imports = []
        for i, line in enumerate(lines, start=1):
            s = line.strip()
            if s.startswith("import "):
                imports.append(s[7:].split(",")[0].strip())
            elif s.startswith("from ") and " import " in s:
                parts = s.split(" import ")
                mod = parts[0][5:].strip()
                imports.append(mod)
            elif s.startswith("def "):
                m = re.match(r"def\s+([a-zA-Z0-9_]+)\s*\(", s)
                if m:
                    symbols.append(SymbolInfo(
                        name=m.group(1),
                        kind="function",
                        file_path=rel_path,
                        line_start=i,
                        line_end=i
                    ))
            elif s.startswith("class "):
                m = re.match(r"class\s+([a-zA-Z0-9_]+)", s)
                if m:
                    symbols.append(SymbolInfo(
                        name=m.group(1),
                        kind="class",
                        file_path=rel_path,
                        line_start=i,
                        line_end=i
                    ))
        return symbols, imports

    def _parse_javascript(self, lines: List[str], rel_path: str) -> Tuple[List[SymbolInfo], List[str]]:
        symbols = []
        imports = []
        for i, line in enumerate(lines, start=1):
            s = line.strip()
            if s.startswith("import ") and "from" in s:
                m = re.search(r"from\s+['\"](.*?)['\"]", s)
                if m:
                    imports.append(m.group(1))
            elif s.startswith("const ") or s.startswith("function "):
                m = re.search(r"(?:const|function)\s+([a-zA-Z0-9_]+)\s*=?\s*(?:async\s*)?\(?", s)
                if m:
                    symbols.append(SymbolInfo(
                        name=m.group(1),
                        kind="function",
                        file_path=rel_path,
                        line_start=i,
                        line_end=i
                    ))
            elif s.startswith("class "):
                m = re.search(r"class\s+([a-zA-Z0-9_]+)", s)
                if m:
                    symbols.append(SymbolInfo(
                        name=m.group(1),
                        kind="class",
                        file_path=rel_path,
                        line_start=i,
                        line_end=i
                    ))
        return symbols, imports

    def _build_caller_graph(self, symbols: Dict[str, SymbolInfo], file_index: Dict[str, FileAnalysis]):
        for caller_name, caller_sym in symbols.items():
            for target_call in caller_sym.calls:
                if target_call in symbols:
                    if caller_name not in symbols[target_call].callers:
                        symbols[target_call].callers.append(caller_name)

    def _ext_to_language(self, ext: str) -> str:
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown"
        }
        return mapping.get(ext, "unknown")

    def _detect_primary_language(self, file_index: Dict[str, FileAnalysis]) -> str:
        counts: Dict[str, int] = {}
        for f in file_index.values():
            if f.language != "unknown":
                counts[f.language] = counts.get(f.language, 0) + 1
        if not counts:
            return "python"
        return max(counts.items(), key=lambda x: x[1])[0]

    def _detect_frameworks(self, file_index: Dict[str, FileAnalysis], config_files: List[str]) -> List[str]:
        frameworks = set()
        for f in file_index.values():
            for imp in f.imports:
                low = imp.lower()
                if "fastapi" in low:
                    frameworks.add("FastAPI")
                elif "flask" in low:
                    frameworks.add("Flask")
                elif "django" in low:
                    frameworks.add("Django")
                elif "express" in low:
                    frameworks.add("Express")
                elif "react" in low:
                    frameworks.add("React")
                elif "sqlalchemy" in low:
                    frameworks.add("SQLAlchemy")
                elif "pydantic" in low:
                    frameworks.add("Pydantic")
                elif "pytest" in low:
                    frameworks.add("pytest")
        return sorted(list(frameworks))

    def _detect_package_manager(self) -> str:
        if os.path.exists(os.path.join(self.repo_path, "uv.lock")):
            return "uv"
        if os.path.exists(os.path.join(self.repo_path, "poetry.lock")):
            return "poetry"
        if os.path.exists(os.path.join(self.repo_path, "package-lock.json")):
            return "npm"
        if os.path.exists(os.path.join(self.repo_path, "yarn.lock")):
            return "yarn"
        if os.path.exists(os.path.join(self.repo_path, "pnpm-lock.yaml")):
            return "pnpm"
        if os.path.exists(os.path.join(self.repo_path, "requirements.txt")):
            return "pip"
        return "pip"

    def _detect_test_framework(self, lang: str, config_files: List[str], test_files: List[str]) -> Tuple[str, str]:
        if lang == "python":
            if any("pytest" in c for c in config_files) or any(t.endswith(".py") for t in test_files):
                return "pytest", "pytest"
            return "unittest", "python -m unittest discover"
        elif lang in {"javascript", "typescript"}:
            if any("vitest" in c for c in config_files):
                return "vitest", "npx vitest run"
            if any("jest" in c for c in config_files):
                return "jest", "npx jest"
            return "npm test", "npm test"
        return "pytest", "pytest"

    def _detect_entry_points(self, file_index: Dict[str, FileAnalysis]) -> List[str]:
        candidates = ["main.py", "app.py", "server.py", "index.js", "index.ts", "server.js", "app.js"]
        found = []
        for c in candidates:
            for path in file_index:
                if path == c or path.endswith("/" + c):
                    found.append(path)
        return found

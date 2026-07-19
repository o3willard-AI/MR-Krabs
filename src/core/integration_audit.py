#!/usr/bin/env python3
"""
Integration Audit (Loop 4) — Static Analysis Pass

Runs after code generation, before the Judge. Catches wiring gaps,
stub placeholders, constraint violations, and dead error paths —
deterministically, with zero LLM cost.

Four checks:
  1. Call Graph: spec-required functions with zero call sites
  2. Stub Detection: TODO, placeholder, mock, stubbed implementations
  3. Import Audit: external packages not in allowed list, undefined names
  4. Error Path: except blocks that swallow errors without recovery
"""

import ast
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


# ── Patterns ──────────────────────────────────────────────────

STUB_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'todo',
        r'fixme',
        r'placeholder',
        r'stub(?!\s*$)',           # "stub" not at end of line
        r'mock\s+(?:data|response|implementation)',
        r'for\s+now[,.]+(?!.*implement)',  # "for now..." (not "for now, implement")
        r'simplified\s+version',
        r'in\s+a\s+real\s+implementation',
        r'would\s+need',
        r'we.ll\s+skip\s+the\s+implementation',
        r'#\s*this\s+is\s+a\s+(?:mock|placeholder|stub)',
        r'return\s+.*?(?:mock|dummy|fake)\s+',
        r'return\s+\[?\s*\].*?#.*(?:placeholder|stub)',
    ]
]

STDLIB_MODULES = {
    'abc', 'aifc', 'argparse', 'array', 'ast', 'asynchat', 'asyncio',
    'asyncore', 'atexit', 'audioop', 'base64', 'bdb', 'binascii', 'binhex',
    'bisect', 'builtins', 'bz2', 'calendar', 'cgi', 'cgitb', 'chunk', 'cmath',
    'cmd', 'code', 'codecs', 'codeop', 'collections', 'colorsys', 'compileall',
    'concurrent', 'configparser', 'contextlib', 'contextvars', 'copy',
    'copyreg', 'cProfile', 'crypt', 'csv', 'ctypes', 'curses', 'dataclasses',
    'datetime', 'dbm', 'decimal', 'difflib', 'dis', 'distutils', 'doctest',
    'email', 'encodings', 'enum', 'errno', 'faulthandler', 'fcntl', 'filecmp',
    'fileinput', 'fnmatch', 'formatter', 'fractions', 'ftplib', 'functools',
    'gc', 'getopt', 'getpass', 'gettext', 'glob', 'grp', 'gzip', 'hashlib',
    'heapq', 'hmac', 'html', 'http', 'idlelib', 'imaplib', 'imghdr', 'imp',
    'importlib', 'inspect', 'io', 'ipaddress', 'itertools', 'json', 'keyword',
    'lib2to3', 'linecache', 'locale', 'logging', 'lzma', 'mailbox', 'mailcap',
    'marshal', 'math', 'mimetypes', 'mmap', 'modulefinder', 'multiprocessing',
    'netrc', 'nis', 'nntplib', 'numbers', 'operator', 'optparse', 'os',
    'ossaudiodev', 'parser', 'pathlib', 'pdb', 'pickle', 'pickletools',
    'pipes', 'pkgutil', 'platform', 'plistlib', 'poplib', 'posix', 'posixpath',
    'pprint', 'profile', 'pstats', 'pty', 'pwd', 'py_compile', 'pyclbr',
    'pydoc', 'queue', 'quopri', 'random', 're', 'readline', 'reprlib',
    'resource', 'rlcompleter', 'runpy', 'sched', 'secrets', 'select',
    'selectors', 'shelve', 'shlex', 'shutil', 'signal', 'site', 'smtpd',
    'smtplib', 'sndhdr', 'socket', 'socketserver', 'sqlite3', 'ssl', 'stat',
    'statistics', 'string', 'stringprep', 'struct', 'subprocess', 'sunau',
    'symtable', 'sys', 'sysconfig', 'syslog', 'tabnanny', 'tarfile',
    'telnetlib', 'tempfile', 'termios', 'test', 'textwrap', 'threading',
    'time', 'timeit', 'tkinter', 'token', 'tokenize', 'trace', 'traceback',
    'tracemalloc', 'tty', 'turtle', 'turtledemo', 'types', 'typing',
    'unicodedata', 'unittest', 'urllib', 'uu', 'uuid', 'venv', 'warnings',
    'wave', 'weakref', 'webbrowser', 'winreg', 'winsound', 'wsgiref',
    'xdrlib', 'xml', 'xmlrpc', 'zipapp', 'zipfile', 'zipimport', 'zlib',
    # Additional stdlib modules not in the full list
    'http.server', 'http.client', 'urllib.request', 'urllib.error',
    'urllib.parse',
}


# ── Data classes ──────────────────────────────────────────────

@dataclass
class Finding:
    """A single audit finding."""
    severity: str           # "error", "warning"
    category: str           # "dead_function", "stub", "bad_import", "missing_import", "swallowed_error"
    file: str
    line: int
    message: str
    fix_instruction: str    # What the coder should do to fix this

@dataclass
class AuditResult:
    """Complete audit result."""
    passed: bool
    findings: List[Finding] = field(default_factory=list)
    summary: str = ""

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "warning"]


# ── Check 1: Call Graph ───────────────────────────────────────

def _extract_function_defs(tree: ast.AST) -> Dict[str, int]:
    """Extract all top-level function definitions: {name: lineno}."""
    defs = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs[node.name] = node.lineno
    return defs

def _extract_call_targets(tree: ast.AST) -> Set[str]:
    """Extract all names called as functions anywhere in the tree."""
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                # self.method() or module.func() — track the method name
                calls.add(node.func.attr)
    return calls

def _extract_required_functions(spec_text: str) -> List[str]:
    """Extract function names the spec says must exist.

    Matches patterns like:
      - `function_name(arg) — description`
      - `Function: function_name`
      - `Implement function_name(`
      - Backtick-quoted function names in spec
    """
    patterns = [
        r'`([a-z_][a-z0-9_]*)\s*\(',           # `func_name(`
        r'(?:Function|Implement|Create)\s+`?([a-z_][a-z0-9_]*)`?',
        r'([a-z_][a-z0-9_]*)\s*\([^)]*\)\s*[—\-]',  # func_name(args) — desc
    ]
    names = set()
    for pattern in patterns:
        for match in re.finditer(pattern, spec_text, re.IGNORECASE):
            names.add(match.group(1))
    return [n for n in names if not n.startswith('_') and len(n) > 2]

def check_call_graph(files: Dict[str, str], spec_text: str) -> List[Finding]:
    """Find spec-required functions that are defined but never called."""
    findings = []
    required = set(_extract_required_functions(spec_text))

    if not required:
        return findings

    # Collect all defs and calls across all files
    all_defs: Dict[str, Tuple[str, int]] = {}    # name -> (file, line)
    all_calls: Set[str] = set()

    for filepath, content in files.items():
        if not filepath.endswith('.py'):
            continue
        try:
            tree = ast.parse(content)
            for name, lineno in _extract_function_defs(tree).items():
                all_defs[name] = (filepath, lineno)
            all_calls.update(_extract_call_targets(tree))
        except SyntaxError:
            continue  # Skip files that don't parse

    # Check required functions
    for name in required:
        if name in all_defs and name not in all_calls:
            filepath, lineno = all_defs[name]
            findings.append(Finding(
                severity="error",
                category="dead_function",
                file=filepath,
                line=lineno,
                message=f"Function '{name}' is defined but never called — required by spec but not wired into execution path",
                fix_instruction=f"Add a call to '{name}()' in the appropriate execution path. "
                               f"If it's an error handler or rollback function, it must be "
                               f"invoked in except blocks or failure branches.",
            ))

    return findings


# ── Check 2: Stub Detection ───────────────────────────────────

def check_stubs(files: Dict[str, str]) -> List[Finding]:
    """Find TODO, placeholder, mock, and stubbed implementations."""
    findings = []

    for filepath, content in files.items():
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern in STUB_PATTERNS:
                if pattern.search(line):
                    findings.append(Finding(
                        severity="error",
                        category="stub",
                        file=filepath,
                        line=i,
                        message=f"Stub detected: '{line.strip()[:80]}'",
                        fix_instruction=f"Replace this stub with the real implementation. "
                                       f"Do not return mock data — implement the actual logic.",
                    ))
                    break  # One finding per line

    return findings


# ── Check 3: Import Audit ─────────────────────────────────────

def _extract_imports(tree: ast.AST) -> List[Tuple[str, int, str]]:
    """Extract all imports: (module_name, lineno, type). type is 'import' or 'from'."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name.split('.')[0], node.lineno, 'import'))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append((node.module.split('.')[0], node.lineno, 'from'))
    return imports

def _extract_undefined_names(tree: ast.AST) -> List[Tuple[str, int]]:
    """Find names used but not imported or defined.
    
    Filters out:
    - Single-letter names (common loop variables)
    - Names used in for-loop targets and except handlers (locally scoped)
    - Names that appear as function parameters
    """
    # Collect all locally scoped names
    locally_scoped = set()
    for node in ast.walk(tree):
        # For-loop targets
        if isinstance(node, (ast.For, ast.AsyncFor)):
            for target in (node.target.elts if isinstance(node.target, ast.Tuple) 
                          else [node.target]):
                if isinstance(target, ast.Name):
                    locally_scoped.add(target.id)
        # Except handlers
        if isinstance(node, ast.ExceptHandler):
            if node.name:
                locally_scoped.add(node.name)
        # Function parameters
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                locally_scoped.add(arg.arg)
            if node.args.vararg:
                locally_scoped.add(node.args.vararg.arg)
            if node.args.kwarg:
                locally_scoped.add(node.args.kwarg.arg)
        # Assignment unpacking
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Tuple):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name):
                            locally_scoped.add(elt.id)

    # Collect all defined names
    defined = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined.add(target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                defined.add(alias.asname or alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                defined.add(alias.asname or alias.name)

    # Collect all used names
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if len(node.id) > 1:  # Skip single-letter names
                used.add(node.id)

    # Built-ins plus common stdlib
    builtins = {
        'print', 'len', 'range', 'int', 'str', 'float', 'bool', 'list', 'dict',
        'set', 'tuple', 'type', 'isinstance', 'issubclass', 'hasattr', 'getattr',
        'setattr', 'delattr', 'object', 'super', 'Exception', 'ValueError',
        'TypeError', 'KeyError', 'IndexError', 'AttributeError', 'OSError',
        'FileNotFoundError', 'ConnectionError', 'RuntimeError', 'NotImplementedError',
        'StopIteration', 'True', 'False', 'None', 'open', 'iter', 'next',
        'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed', 'any', 'all',
        'sum', 'min', 'max', 'abs', 'round', 'id', 'repr', 'bytes', 'bytearray',
        'chr', 'ord', 'hex', 'oct', 'bin', 'input', 'format', 'property',
        'staticmethod', 'classmethod', '__import__', '__name__', '__file__',
        '__doc__', '__builtins__', 'exit', 'quit',
        'KeyboardInterrupt', 'SystemExit', 'GeneratorExit', 'MemoryError',
        'BufferError', 'Warning', 'UserWarning', 'DeprecationWarning',
        'PendingDeprecationWarning', 'SyntaxWarning', 'RuntimeWarning',
        'FutureWarning', 'ImportWarning', 'UnicodeWarning', 'BytesWarning',
        'ResourceWarning', 'OSError', 'TimeoutError', 'ConnectionError',
        'ConnectionRefusedError', 'ConnectionResetError', 'BrokenPipeError',
        'BlockingIOError', 'InterruptedError', 'IsADirectoryError',
        'NotADirectoryError', 'PermissionError', 'ProcessLookupError',
        'FileExistsError', 'ChildProcessError',
        'ArithmeticError', 'FloatingPointError', 'OverflowError',
        'ZeroDivisionError', 'ModuleNotFoundError', 'NameError',
        'UnboundLocalError', 'LookupError', 'RecursionError', 'ReferenceError',
        'UnicodeError', 'UnicodeDecodeError', 'UnicodeEncodeError',
        'UnicodeTranslateError', 'AssertionError', 'EOFError', 'ImportError',
        'IndentationError', 'TabError', 'NotImplemented', 'Ellipsis',
        'EnvironmentError', 'IOError',
        # Context manager targets
        'tmp_f', 'tmp_path', 'tmp_dir',
    }

    undefined = []
    for name in sorted(used - defined - builtins - locally_scoped):
        # Find first use location
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load):
                undefined.append((name, node.lineno))
                break

    return undefined

def _extract_allowed_from_spec(spec_text: str) -> Set[str]:
    """Extract allowed packages from spec text.

    Matches patterns like:
      - "stdlib only"
      - "zero external dependencies"
      - "allowed: requests, pytest"
      - "use os, shutil, json"
    """
    allowed = set()
    # If spec says "stdlib only" or "zero dependencies" or "no external"
    if re.search(
        r'(?:stdlib\s+only|zero\s+(?:external\s+)?dependenc|no\s+external\s+(?:package|depend))',
        spec_text, re.IGNORECASE
    ):
        # Only stdlib is allowed
        return {'__STDLIB_ONLY__'}

    # Look for explicit allow lists
    allow_match = re.search(
        r'(?:allowed|permitted|use)\s*(?:packages?|libraries?|dependencies?)?\s*:\s*([^\n]+)',
        spec_text, re.IGNORECASE
    )
    if allow_match:
        allowed.update(
            p.strip().strip('`').strip('"').strip("'")
            for p in re.split(r'[,;]', allow_match.group(1))
            if p.strip()
        )

    return allowed

def check_imports(files: Dict[str, str], spec_text: str) -> List[Finding]:
    """Find imports that violate dependency constraints and undefined names."""
    findings = []
    allowed = _extract_allowed_from_spec(spec_text)
    stdlib_only = '__STDLIB_ONLY__' in allowed

    for filepath, content in files.items():
        if not filepath.endswith('.py'):
            continue
        is_test = 'test' in os.path.basename(filepath).lower()
        try:
            tree = ast.parse(content)

            # Check external imports (skip test files — pytest and local imports are expected)
            if not is_test:
                for module, lineno, imp_type in _extract_imports(tree):
                    if module in STDLIB_MODULES:
                        continue  # Always allowed
                    if stdlib_only:
                        findings.append(Finding(
                            severity="error",
                            category="bad_import",
                            file=filepath,
                            line=lineno,
                            message=f"External dependency '{module}' — spec requires stdlib only",
                            fix_instruction=f"Replace '{module}' with stdlib equivalent. "
                                           f"For HTTP: use urllib.request instead of requests. "
                                           f"For YAML: use a simple parser or json instead.",
                        ))
                    elif allowed and module not in allowed:
                        findings.append(Finding(
                            severity="error",
                            category="bad_import",
                            file=filepath,
                            line=lineno,
                            message=f"Import '{module}' not in allowed list: {allowed}",
                            fix_instruction=f"Remove import of '{module}' or add it to the spec's allowed list.",
                        ))

            # Check undefined names
            for name, lineno in _extract_undefined_names(tree):
                findings.append(Finding(
                    severity="error",
                    category="missing_import",
                    file=filepath,
                    line=lineno,
                    message=f"Name '{name}' is used but never imported or defined",
                    fix_instruction=f"Add 'import {name}' at the top of {filepath}, "
                                   f"or define '{name}' before use.",
                ))

        except SyntaxError:
            pass

    return findings


# ── Check 4: Error Path Analysis ──────────────────────────────

def _find_except_blocks(tree: ast.AST) -> List[Tuple[int, int, List[str], List[ast.stmt]]]:
    """Find all except blocks: (start_line, end_line, exception_types, body)."""
    blocks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                types = []
                if handler.type:
                    if isinstance(handler.type, ast.Tuple):
                        types = [ast.dump(t) for t in handler.type.elts]
                    else:
                        types = [ast.dump(handler.type)]
                blocks.append((
                    handler.lineno,
                    handler.end_lineno or handler.lineno,
                    types,
                    handler.body,
                ))
    return blocks

def _body_has_recovery(body: List[ast.stmt]) -> bool:
    """Check if an except body has any recovery action (raise, return, log, rollback)."""
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, ast.Return):
            return True
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                # self.logger.error, print, etc.
                name = node.func.attr
                if name in ('error', 'warning', 'critical', 'log', 'rollback',
                           'recover', 'cleanup', 'restore', 'reset'):
                    return True
            elif isinstance(node.func, ast.Name):
                if node.func.id in ('print', 'rollback', 'recover', 'cleanup',
                                   'restore', 'reset', 'log_telemetry'):
                    return True
    return False

def check_error_paths(files: Dict[str, str]) -> List[Finding]:
    """Find except blocks that swallow errors without recovery."""
    findings = []

    for filepath, content in files.items():
        if not filepath.endswith('.py'):
            continue
        try:
            tree = ast.parse(content)

            for start_line, end_line, types, body in _find_except_blocks(tree):
                # Skip except blocks that catch specific errors and re-raise
                if 'Exception' not in str(types) and _body_has_recovery(body):
                    continue

                # Flag bare except or except Exception with no recovery
                if not types or 'Exception' in str(types):
                    if not _body_has_recovery(body):
                        # Check if body is just 'pass'
                        if len(body) == 1 and isinstance(body[0], ast.Pass):
                            severity = "error"
                            msg = "Bare 'pass' in except block — errors silently swallowed"
                            fix = "Add error recovery: re-raise, log the error, or invoke rollback/cleanup."
                        else:
                            severity = "warning"
                            msg = "Except block has no visible recovery action (raise, log, rollback)"
                            fix = "Add at minimum a log statement. For critical paths, invoke cleanup or rollback."
                        findings.append(Finding(
                            severity=severity,
                            category="swallowed_error",
                            file=filepath,
                            line=start_line,
                            message=msg,
                            fix_instruction=fix,
                        ))

        except SyntaxError:
            pass

    return findings


# ── Main Audit Runner ─────────────────────────────────────────

def run_audit(
    files: Dict[str, str],
    spec_text: str,
    project_root: str = ".",
) -> AuditResult:
    """Run all four audit checks and return findings.

    Args:
        files: Dict of {filepath: content} for all generated files
        spec_text: The original task specification
        project_root: Root directory for resolving relative paths

    Returns:
        AuditResult with passed=True only if zero error-severity findings
    """
    all_findings: List[Finding] = []

    # Check 1: Call graph
    try:
        all_findings.extend(check_call_graph(files, spec_text))
    except Exception as e:
        all_findings.append(Finding(
            severity="warning", category="audit_internal",
            file="", line=0,
            message=f"Call graph check failed: {e}",
            fix_instruction=""
        ))

    # Check 2: Stub detection
    try:
        all_findings.extend(check_stubs(files))
    except Exception as e:
        all_findings.append(Finding(
            severity="warning", category="audit_internal",
            file="", line=0,
            message=f"Stub check failed: {e}",
            fix_instruction=""
        ))

    # Check 3: Import audit
    try:
        all_findings.extend(check_imports(files, spec_text))
    except Exception as e:
        all_findings.append(Finding(
            severity="warning", category="audit_internal",
            file="", line=0,
            message=f"Import check failed: {e}",
            fix_instruction=""
        ))

    # Check 4: Error path analysis
    try:
        all_findings.extend(check_error_paths(files))
    except Exception as e:
        all_findings.append(Finding(
            severity="warning", category="audit_internal",
            file="", line=0,
            message=f"Error path check failed: {e}",
            fix_instruction=""
        ))

    # Check 5: Requirement coverage
    try:
        all_findings.extend(check_requirements(files, spec_text))
    except Exception as e:
        all_findings.append(Finding(
            severity="warning", category="audit_internal",
            file="", line=0,
            message=f"Requirement check failed: {e}",
            fix_instruction=""
        ))

    errors = [f for f in all_findings if f.severity == "error"]
    warnings = [f for f in all_findings if f.severity == "warning"]

    passed = len(errors) == 0

    if passed and not warnings:
        summary = "All integration checks passed"
    elif passed:
        summary = f"Passed with {len(warnings)} warning(s)"
    else:
        summary = f"FAILED: {len(errors)} error(s), {len(warnings)} warning(s)"

    return AuditResult(passed=passed, findings=all_findings, summary=summary)


# ── Format for coder feedback ─────────────────────────────────

def format_findings_for_coder(result: AuditResult) -> str:
    """Format audit findings as actionable fix instructions for the coder tier."""

    if result.passed and not result.findings:
        return ""

    lines = ["## Integration Audit Findings", ""]

    by_category = {}
    for f in result.findings:
        by_category.setdefault(f.category, []).append(f)

    for category, findings in sorted(by_category.items()):
        lines.append(f"### {category.replace('_', ' ').title()} ({len(findings)})")
        lines.append("")
        for f in findings[:10]:  # Cap at 10 per category
            lines.append(f"- **{f.file}:{f.line}** [{f.severity}] {f.message}")
            lines.append(f"  → Fix: {f.fix_instruction}")
        if len(findings) > 10:
            lines.append(f"  ... and {len(findings) - 10} more")
        lines.append("")

    lines.append("**Action required**: Fix all ERROR-severity findings above, then re-submit.")
    return "\n".join(lines)


# ── Check 5: Requirement Coverage ────────────────────────────────

def _extract_requirement_names(spec_text: str) -> list[tuple[str, str]]:
    """Extract requirement-like function/endpoint names from spec.

    Returns list of (name, requirement_type) tuples.
    requirement_type: 'must_call', 'must_implement', 'must_define'
    """
    reqs = []

    # Pattern: "Implement X(name)" or "Create X() that Y"
    impl_patterns = [
        r'(?:Implement|Create|Build|Write)\s+`?(\w+)`?\s*\(',
        r'(?:function|method)\s+`?(\w+)`?\s*\(',
        r'`(\w+)\([^)]*\)`\s*[-—–]\s*\w+',
    ]
    for pattern in impl_patterns:
        for match in re.finditer(pattern, spec_text, re.IGNORECASE):
            name = match.group(1)
            if len(name) > 2 and not name.startswith('_'):
                reqs.append((name, 'must_define'))

    # Pattern: "MUST call X()" or "should use Y()"
    call_patterns = [
        r'(?:must|should|shall)\s+(?:call|use|invoke|query)\s+`?(\w+)`?\s*\(',
        r'(?:calls?|uses?|invokes?|queries?)\s+`?(\w+)`?\s*\(',
    ]
    for pattern in call_patterns:
        for match in re.finditer(pattern, spec_text, re.IGNORECASE):
            name = match.group(1)
            if len(name) > 2:
                reqs.append((name, 'must_call'))

    # Deduplicate
    seen = set()
    unique = []
    for name, rtype in reqs:
        key = (name.lower(), rtype)
        if key not in seen:
            seen.add(key)
            unique.append((name, rtype))

    return unique


def check_requirements(files: dict[str, str], spec_text: str) -> list[Finding]:
    """Verify that spec-required functions/endpoints exist and are called.

    For each requirement extracted from the spec:
    - 'must_define': verify the function/endpoint EXISTS in the files
    - 'must_call': verify the function/endpoint is CALLED somewhere
    """
    findings = []
    reqs = _extract_requirement_names(spec_text)
    if not reqs:
        return findings

    # Collect all defined names and call sites from all files
    all_defs = {}
    all_calls = set()
    for filepath, content in files.items():
        if not filepath.endswith('.py'):
            continue
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    all_defs[node.name.lower()] = (filepath, node.lineno)
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        all_calls.add(node.func.id.lower())
                    elif isinstance(node.func, ast.Attribute):
                        all_calls.add(node.func.attr.lower())
            # Also check for route decorators
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for decorator in node.decorator_list:
                        if isinstance(decorator, ast.Call):
                            if isinstance(decorator.func, ast.Attribute):
                                all_defs[f"/{node.name}"] = (filepath, node.lineno)
        except SyntaxError:
            continue

    for name, rtype in reqs:
        name_lower = name.lower()
        if rtype == 'must_define':
            if name_lower not in all_defs and not any(
                name_lower in d for d in all_defs
            ):
                findings.append(Finding(
                    severity="error",
                    category="requirement_missing",
                    file="",
                    line=0,
                    message=f"Required function/endpoint '{name}' is not defined in any file",
                    fix_instruction=f"Implement '{name}()' as specified in the requirements.",
                ))
        elif rtype == 'must_call':
            if name_lower in all_defs and name_lower not in all_calls:
                fpath, lineno = all_defs[name_lower]
                findings.append(Finding(
                    severity="error",
                    category="requirement_dead",
                    file=fpath,
                    line=lineno,
                    message=f"'{name}()' is defined but never called — spec requires it to be invoked",
                    fix_instruction=f"Add a call to '{name}()' in the execution path that needs it.",
                ))

    return findings

"""Tripwire: fail if the application code imports email or network modules.

This catches obvious accidents only. It is not proof that the program cannot
send messages: a third-party library or code this check does not recognise
could still reach the network. The primary check is a human code and
dependency review (see docs/intent.md).
"""

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "src"
FORBIDDEN = {
    "smtplib", "email", "socket", "http", "urllib", "requests", "ftplib",
    "imaplib", "poplib", "ssl", "xmlrpc", "webbrowser", "subprocess",
}


def risky_imports(source_code):
    """Return forbidden or dynamic imports found in Python source code."""
    found = []
    for node in ast.walk(ast.parse(source_code)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "__import__":
            names = ["__import__"]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if top in FORBIDDEN or top in {"importlib", "__import__"}:
                found.append(name)
    return found


def test_tripwire_detects_forbidden_imports():
    assert risky_imports("import smtplib\nfrom urllib.request import urlopen\n") == [
        "smtplib",
        "urllib.request",
    ]
    assert risky_imports("__import__('socket')") == ["__import__"]
    assert risky_imports("import csv\nimport re\n") == []


def test_application_code_has_no_email_or_network_imports():
    files = sorted(SOURCE.rglob("*.py"))
    assert files, "no source files found"
    for path in files:
        assert risky_imports(path.read_text(encoding="utf-8")) == [], path

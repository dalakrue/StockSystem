"""Create a complete, reproducible static inventory of the application package.

Every file is hashed. Text files are decoded and inspected; Python files are
parsed with AST; SQLite and DuckDB files are opened read-only for schema
inventory. The report does not execute trading calculations.
"""
from __future__ import annotations

import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
JSON_OUT = ROOT / "FULL_PROJECT_INSPECTION_20260621.json"
MD_OUT = ROOT / "FULL_PROJECT_INSPECTION_20260621.md"
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".git"}
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".ini",
    ".cfg", ".csv", ".sql", ".bat", ".ps1", ".src", ".gitignore",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_details(path: Path, raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    details: dict[str, Any] = {
        "line_count": text.count("\n") + (1 if text else 0),
        "replacement_characters": text.count("\ufffd"),
        "absolute_windows_paths": bool(re.search(r"[A-Za-z]:[\\/]Users[\\/]", text)),
    }
    if path.suffix.lower() == ".py":
        try:
            tree = ast.parse(text, filename=str(path))
            imports: list[str] = []
            functions: list[str] = []
            classes: list[str] = []
            calls = Counter()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                elif isinstance(node, ast.Call):
                    name = ""
                    if isinstance(node.func, ast.Attribute):
                        base = node.func.value.id if isinstance(node.func.value, ast.Name) else ""
                        name = f"{base}.{node.func.attr}" if base else node.func.attr
                    elif isinstance(node.func, ast.Name):
                        name = node.func.id
                    if name:
                        calls[name] += 1
            details.update({
                "python_parse_ok": True,
                "imports": sorted(set(imports)),
                "functions": functions,
                "classes": classes,
                "streamlit_calls": {k: v for k, v in sorted(calls.items()) if k.startswith("st.")},
                "cache_calls": {k: v for k, v in sorted(calls.items()) if "cache" in k.lower()},
                "button_calls": sum(v for k, v in calls.items() if k in {"st.button", "button", "form_submit_button", "st.form_submit_button"}),
            })
        except SyntaxError as exc:
            details.update({"python_parse_ok": False, "syntax_error": f"{exc.msg} line {exc.lineno}"})
    return details


def sqlite_schema(path: Path) -> dict[str, Any]:
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        tables = conn.execute("SELECT name, type, sql FROM sqlite_master WHERE type IN ('table','view','index') ORDER BY type,name").fetchall()
        result: dict[str, Any] = {"objects": []}
        for name, kind, sql in tables:
            item: dict[str, Any] = {"name": name, "type": kind, "sql": sql}
            if kind == "table" and not str(name).startswith("sqlite_"):
                item["columns"] = [dict(zip(("cid", "name", "type", "notnull", "default", "pk"), row)) for row in conn.execute(f'PRAGMA table_info("{name}")').fetchall()]
                try:
                    item["row_count"] = int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
                except Exception as exc:
                    item["row_count_error"] = str(exc)
            result["objects"].append(item)
        return result
    finally:
        conn.close()


def duckdb_schema(path: Path) -> dict[str, Any]:
    try:
        import duckdb
    except Exception as exc:
        return {"error": f"duckdb unavailable: {exc}"}
    conn = duckdb.connect(str(path), read_only=True)
    try:
        names = [str(row[0]) for row in conn.execute("SHOW TABLES").fetchall()]
        objects = []
        for name in names:
            item: dict[str, Any] = {"name": name}
            try:
                item["columns"] = [dict(zip(("cid", "name", "type", "notnull", "default", "pk"), row)) for row in conn.execute(f"PRAGMA table_info('{name}')").fetchall()]
                item["row_count"] = int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
            except Exception as exc:
                item["error"] = str(exc)
            objects.append(item)
        return {"objects": objects}
    finally:
        conn.close()


def main() -> int:
    files: list[dict[str, Any]] = []
    syntax_errors: list[str] = []
    extension_counts: Counter[str] = Counter()
    total_bytes = 0
    database_inventory: dict[str, Any] = {}

    candidates = sorted(
        p for p in ROOT.rglob("*")
        if p.is_file() and not any(part in SKIP_PARTS for part in p.relative_to(ROOT).parts)
        and p not in {JSON_OUT, MD_OUT}
    )
    for path in candidates:
        relative = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        suffix = path.suffix.lower() or "<none>"
        extension_counts[suffix] += 1
        total_bytes += len(raw)
        item: dict[str, Any] = {
            "path": relative,
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "suffix": suffix,
        }
        if suffix in TEXT_SUFFIXES or path.name in {".gitignore", ".python-version"}:
            item.update(text_details(path, raw))
            if item.get("python_parse_ok") is False:
                syntax_errors.append(relative)
        files.append(item)
        try:
            if suffix in {".sqlite", ".sqlite3", ".db"}:
                database_inventory[relative] = {"engine": "sqlite", **sqlite_schema(path)}
            elif suffix == ".duckdb":
                database_inventory[relative] = {"engine": "duckdb", **duckdb_schema(path)}
        except Exception as exc:
            database_inventory[relative] = {"error": str(exc)}

    python_files = [item for item in files if item["suffix"] == ".py"]
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root_name": ROOT.name,
        "summary": {
            "file_count": len(files),
            "total_bytes": total_bytes,
            "python_file_count": len(python_files),
            "python_syntax_errors": syntax_errors,
            "extension_counts": dict(extension_counts.most_common()),
            "database_file_count": len(database_inventory),
            "absolute_windows_path_files": [item["path"] for item in files if item.get("absolute_windows_paths")],
        },
        "entrypoint": {
            "app_py_exists": (ROOT / "app.py").exists(),
            "runtime": (ROOT / "runtime.txt").read_text(encoding="utf-8").strip() if (ROOT / "runtime.txt").exists() else None,
        },
        "databases": database_inventory,
        "files": files,
    }
    JSON_OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    summary = report["summary"]
    md = [
        "# Full Project Inspection — 2026-06-21",
        "",
        "This inventory hashes every packaged file, reads every text/configuration file, parses every Python module, and inventories each readable SQLite/DuckDB schema without executing trading calculations.",
        "",
        "## Coverage",
        "",
        f"- Files inspected: **{summary['file_count']:,}**",
        f"- Bytes inspected: **{summary['total_bytes']:,}**",
        f"- Python files parsed: **{summary['python_file_count']:,}**",
        f"- Python syntax errors: **{len(summary['python_syntax_errors'])}**",
        f"- Database files inventoried: **{summary['database_file_count']}**",
        f"- Absolute local Windows-path findings: **{len(summary['absolute_windows_path_files'])}**",
        "",
        "## Entrypoint and runtime",
        "",
        f"- `app.py`: {'present' if report['entrypoint']['app_py_exists'] else 'missing'}",
        f"- `runtime.txt`: `{report['entrypoint']['runtime']}`",
        "",
        "## Extension inventory",
        "",
        "| Extension | Files |",
        "|---|---:|",
    ]
    md.extend(f"| `{ext}` | {count:,} |" for ext, count in summary["extension_counts"].items())
    md += [
        "",
        "## Database inventory",
        "",
        "| File | Engine | Objects |",
        "|---|---|---:|",
    ]
    for name, data in database_inventory.items():
        md.append(f"| `{name}` | {data.get('engine','error')} | {len(data.get('objects', []))} |")
    md += [
        "",
        "## Machine-readable detail",
        "",
        "See `FULL_PROJECT_INSPECTION_20260621.json` for per-file SHA-256, size, line count, Python imports/functions/classes/Streamlit calls, and complete database object metadata.",
        "",
        "## Interpretation boundary",
        "",
        "Static inspection proves package coverage and source integrity. Runtime behavior is covered separately by automated tests, import/compile checks, and the Streamlit startup health test.",
    ]
    MD_OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return 1 if syntax_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

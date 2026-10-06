#!/usr/bin/env python3
"""Verify (or regenerate with --write) the repository source set against SOURCE_MANIFEST.json."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = "profile-migration-source-manifest/v1"
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
EXCLUDED_NAMES = {".DS_Store"}
MANIFEST = "SOURCE_MANIFEST.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_entries(root: Path) -> list[dict]:
    entries = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if (not path.is_file() or path.name == MANIFEST or path.name in EXCLUDED_NAMES
                or any(part in EXCLUDED_PARTS for part in rel.parts)):
            continue
        entries.append({"relative_path": rel.as_posix(), "sha256": sha256(path), "size": path.stat().st_size})
    return entries


def file_set_sha256(entries: list[dict]) -> str:
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="regenerate the manifest instead of verifying")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    actual = source_entries(root)
    if args.write:
        payload = {"schema": SCHEMA, "file_set_sha256": file_set_sha256(actual), "files": actual}
        (root / MANIFEST).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"status": "WRITTEN", "files": len(actual)}, sort_keys=True))
        return 0
    payload = json.loads((root / MANIFEST).read_text())
    ok = (payload.get("schema") == SCHEMA and payload.get("files") == actual
          and payload.get("file_set_sha256") == file_set_sha256(actual))
    status = "PASS" if ok else "FAIL"
    print(json.dumps({"status": status, "files": len(actual), "production_mutations": 0}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

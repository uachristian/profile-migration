#!/usr/bin/env python3
"""Verify inventory-manifest files without returning their contents."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_target(root: Path, rel: str) -> Path:
    posix = PurePosixPath(rel)
    if posix.is_absolute() or not posix.parts or any(p in {"", ".", ".."} for p in posix.parts):
        raise ValueError("unsafe relative path in manifest")
    target = root.joinpath(*posix.parts)
    resolved_parent = target.parent.resolve()
    if root != resolved_parent and root not in resolved_parent.parents:
        raise ValueError("manifest path escapes root")
    return target


def verify(
    root: Path,
    manifest: dict,
    classes: set[str] | None,
    check_mode: bool,
    allow_excluded_secret_suspects: bool = False,
) -> dict:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError("verification root does not exist")
    if not isinstance(manifest, dict) or manifest.get("schema") != "hermes-profile-inventory/v1":
        raise ValueError("unsupported or missing inventory schema")
    entries = manifest.get("files")
    summary = manifest.get("summary")
    if not isinstance(entries, list) or not isinstance(summary, dict):
        raise ValueError("manifest files/summary structure is invalid")
    canonical_files = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    calculated_file_set = hashlib.sha256(canonical_files).hexdigest()
    if summary.get("file_set_sha256") != calculated_file_set:
        raise ValueError("manifest file-set identity mismatch")

    failures = []
    if summary.get("errors", 0):
        failures.append({"relative_path": None, "failure": "source-inventory-errors"})
    if summary.get("snapshot_required_databases", 0):
        failures.append({"relative_path": None, "failure": "source-snapshot-required"})
    if summary.get("secret_suspects", 0) and not allow_excluded_secret_suspects:
        failures.append({"relative_path": None, "failure": "source-secret-suspects-unresolved"})
    checked = 0
    checked_bytes = 0
    seen_all: set[str] = set()
    eligible_classes: set[str] = set()
    selected_entries: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            failures.append({"relative_path": None, "failure": "invalid-entry"})
            continue
        rel = entry.get("relative_path")
        if not isinstance(rel, str) or not rel:
            failures.append({"relative_path": None, "failure": "invalid-path"})
            continue
        if rel in seen_all:
            failures.append({"relative_path": rel, "failure": "duplicate-manifest-path"})
            continue
        seen_all.add(rel)
        if entry.get("type") != "file" or not entry.get("transfer_eligible"):
            continue
        classification = entry.get("classification")
        eligible_classes.add(classification)
        required_ok = (
            isinstance(classification, str)
            and isinstance(entry.get("size"), int)
            and isinstance(entry.get("sha256"), str)
            and len(entry["sha256"]) == 64
            and all(c in "0123456789abcdef" for c in entry["sha256"].lower())
            and isinstance(entry.get("mode"), str)
            and len(entry["mode"]) == 4
            and all(c in "01234567" for c in entry["mode"])
        )
        if not required_ok:
            failures.append({"relative_path": rel, "failure": "invalid-transfer-entry"})
            continue
        if classes is None or classification in classes:
            selected_entries.append(entry)

    if classes is not None:
        unknown = sorted(classes - eligible_classes)
        for name in unknown:
            failures.append({"relative_path": None, "failure": "unknown-class-selection", "classification": name})

    for entry in selected_entries:
        rel = entry["relative_path"]
        target = safe_target(root, rel)
        checked += 1
        if not target.exists():
            failures.append({"relative_path": rel, "failure": "missing"})
            continue
        if target.is_symlink() or not target.is_file():
            failures.append({"relative_path": rel, "failure": "unexpected-type"})
            continue
        try:
            st = target.stat()
            checked_bytes += st.st_size
            if st.st_size != entry["size"]:
                failures.append({"relative_path": rel, "failure": "size-mismatch"})
                continue
            if sha256_file(target) != entry["sha256"]:
                failures.append({"relative_path": rel, "failure": "hash-mismatch"})
                continue
            if check_mode and f"{stat.S_IMODE(st.st_mode):04o}" != entry["mode"]:
                failures.append({"relative_path": rel, "failure": "mode-mismatch"})
        except OSError:
            failures.append({"relative_path": rel, "failure": "unreadable"})
    if not selected_entries:
        failures.append({"relative_path": None, "failure": "empty-transfer-set"})
    if checked != len(selected_entries):
        failures.append({"relative_path": None, "failure": "checked-count-mismatch"})
    manifest_identity = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema": "hermes-manifest-verification/v2",
        "read_only": True,
        "root": str(root),
        "manifest_identity_sha256": manifest_identity,
        "manifest_file_set_sha256": calculated_file_set,
        "selected_classes": None if classes is None else sorted(classes),
        "allowed_excluded_secret_suspects": allow_excluded_secret_suspects,
        "expected_files": len(selected_entries),
        "checked_files": checked,
        "checked_bytes": checked_bytes,
        "failure_count": len(failures),
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }


def write_owner_only(path: Path, payload: dict) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("output parent must be a real directory")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(parent))
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fd = -1
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
    except Exception:
        if fd >= 0:
            os.close(fd)
        temp_path.unlink(missing_ok=True)
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify files against Hermes migration inventory")
    ap.add_argument("--root", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--classes", help="comma-separated classifications; default all transfer-eligible")
    ap.add_argument("--ignore-mode", action="store_true", help="skip permission-mode parity only when the contract explicitly allows it")
    ap.add_argument(
        "--allow-excluded-secret-suspects",
        action="store_true",
        help="continue only after the contract explicitly adjudicates the listed suspect paths; they remain excluded",
    )
    ap.add_argument("--no-timestamp", action="store_true")
    args = ap.parse_args()
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        classes = {x.strip() for x in args.classes.split(",") if x.strip()} if args.classes is not None else None
        if args.classes is not None and not classes:
            raise ValueError("class selection is empty")
        result = verify(
            Path(args.root), manifest, classes, not args.ignore_mode,
            allow_excluded_secret_suspects=args.allow_excluded_secret_suspects,
        )
        if not args.no_timestamp:
            result["generated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        write_owner_only(Path(args.output), result)
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "error_class": type(exc).__name__}), file=sys.stderr)
        return 2
    print(json.dumps({k: result[k] for k in ("status", "checked_files", "checked_bytes", "failure_count")}, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

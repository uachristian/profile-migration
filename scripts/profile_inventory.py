#!/usr/bin/env python3
"""Read-only Hermes profile inventory for migration planning.

Produces paths, classes, sizes, hashes, modes, and bounded SQLite health.
Never emits file contents or detected secret values.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import tempfile
import urllib.parse
from pathlib import Path, PurePosixPath

SECRET_EXACT = {
    ".env", ".npmrc", ".pypirc", ".netrc", ".git-credentials", ".dockerconfigjson",
    "auth.json", "credentials.json", "secrets.json", "service-account.json", "docker-config.json",
    "id_rsa", "id_ed25519", "id_ecdsa", "keychain-export.json", "cookies.sqlite", "cookies.json",
}
SECRET_NAME_PARTS = ("password", "passwd", "credential", "private-key", "private_key")
SECRET_SUFFIXES = (".p12", ".pfx", ".pem")
DERIVED_COMPONENTS = {
    ".git", "node_modules", "__pycache__", ".cache", "cache", "caches",
    ".venv", "venv", "dist", "build", ".pytest_cache", ".mypy_cache",
    "coverage", ".coverage", "tmp", "temp", ".npm", "lazy-packages",
    "worktrees", "_worktrees", "releases", "preview",
}
RECOVERY_COMPONENTS = {
    "backups", "_backups", "state-snapshots", "checkpoints", "recovery",
    "rollback", "restore-drill", "quarantine", "_quarantine", "reviews", "outbox",
}
# Directory/file name prefixes treated as recovery material (never migrated).
# Extend per site with --recovery-prefix or PROFILE_MIGRATION_RECOVERY_PREFIXES
# (comma-separated); both add to these defaults.
DEFAULT_RECOVERY_PREFIXES = ("backup", "recovery", "snapshot", "restore", "rollback")
RECOVERY_PREFIX_ENV = "PROFILE_MIGRATION_RECOVERY_PREFIXES"


def resolve_recovery_prefixes(extra: list[str] | None = None) -> tuple[str, ...]:
    env = [p.strip().lower() for p in os.environ.get(RECOVERY_PREFIX_ENV, "").split(",")]
    cli = [p.strip().lower() for p in (extra or [])]
    merged = list(DEFAULT_RECOVERY_PREFIXES)
    for prefix in env + cli:
        if prefix and prefix not in merged:
            merged.append(prefix)
    return tuple(merged)


RECOVERY_PREFIXES = DEFAULT_RECOVERY_PREFIXES
RUNTIME_COMPONENTS = {"logs", "locks", "pids"}
RUNTIME_TOP_LEVEL = {"home", ".local", "bin"}
RUNTIME_NAMES = {
    "gateway_state.json", "gateway.lock", "gateway.pid", "gateway.sock",
    "active_profile", "update_state.json", "models_dev_cache.json",
}
SOURCE_LOCKFILES = {"uv.lock", "poetry.lock", "pdm.lock", "bun.lock", "bun.lockb"}
DYNAMIC_DB_NAMES = {"state.db", "projects.db", "kanban.db", "executions.db"}
AUTHORITY_ROOTS = {"cron", "plugins", "scripts", "hooks", "mcp", "launchd", "systemd"}
REVIEW_CONFIG_NAMES = {"config.yaml", "config.yml", "mcp.json", "profile.yaml", "distribution.yaml"}
SCAN_CHUNK = 1024 * 1024
SCAN_OVERLAP = 4096
ASSIGNMENT_RE = re.compile(
    rb"(?im)(?:^|[,{])\s*[\"']?([A-Z0-9_./:-]*(?:ACCESS_TOKEN|REFRESH_TOKEN|AUTH_TOKEN|TOKEN|CLIENT_SECRET|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY)[A-Z0-9_./:-]*)[\"']?\s*[:=]\s*[\"']?([^\"'\s,#}\]]{8,})"
)
REFERENCE_KEY_SUFFIXES = (b"_FILE", b"_PATH", b"_REF", b"_ENV", b"_VAR")
PRIVATE_KEY_RE = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
TOKEN_PREFIX_RE = re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{24,})")
PLACEHOLDER_PREFIXES = (b"${", b"<", b"[redacted", b"redacted", b"changeme", b"example", b"dummy", b"fixture")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def mode_string(path: Path, follow_symlinks: bool = False) -> str:
    return f"{stat.S_IMODE(path.stat(follow_symlinks=follow_symlinks).st_mode):04o}"


def classify_path(rel: str, recovery_prefixes: tuple[str, ...] | None = None) -> str:
    prefixes = RECOVERY_PREFIXES if recovery_prefixes is None else recovery_prefixes
    parts = [p.lower() for p in PurePosixPath(rel).parts]
    normalized = [p.lstrip("._-") for p in parts]
    name = parts[-1]
    if parts and parts[0] == "profiles":
        return "excluded-sibling-profiles"
    if (
        name in SECRET_EXACT
        or name.startswith(".env.")
        or name.endswith(SECRET_SUFFIXES)
        or any(term in name for term in SECRET_NAME_PARTS)
    ):
        return "excluded-secret"
    if name.endswith(("-wal", "-shm", "-journal")):
        return "excluded-database-sidecar"
    if len(parts) >= 3 and parts[:3] == ["database", "postgres", "data"]:
        return "excluded-dynamic-database-tree"
    if parts and parts[0] in RUNTIME_TOP_LEVEL:
        return "excluded-runtime"
    if any(p in DERIVED_COMPONENTS for p in parts):
        return "excluded-derived"
    if any(p in RECOVERY_COMPONENTS for p in parts) or any(
        n.startswith(prefix) for n in normalized for prefix in prefixes
    ):
        return "excluded-recovery"
    if any(p in RUNTIME_COMPONENTS for p in parts) or name in RUNTIME_NAMES:
        return "excluded-runtime"
    if name.endswith((".sock", ".pid")) or (name.endswith(".lock") and name not in SOURCE_LOCKFILES):
        return "excluded-runtime"
    if name in DYNAMIC_DB_NAMES:
        return "dynamic-database"
    if name in REVIEW_CONFIG_NAMES:
        return "review-config"
    if parts and parts[0] in AUTHORITY_ROOTS:
        return "authority-review"
    return "substantive"


def _chunk_secret_suspect(data: bytes, structured: bool) -> bool:
    if PRIVATE_KEY_RE.search(data) or TOKEN_PREFIX_RE.search(data):
        return True
    if not structured:
        return False
    for match in ASSIGNMENT_RE.finditer(data):
        key = match.group(1).upper()
        value = match.group(2).strip().lower()
        if key.endswith(REFERENCE_KEY_SUFFIXES):
            continue
        if not value or value.startswith(PLACEHOLDER_PREFIXES):
            continue
        if value in {b"true", b"false", b"none", b"null", b"disabled"}:
            continue
        return True
    return False


def content_secret_suspect(path: Path, size: int) -> bool:
    if size <= 0:
        return False
    structured = True  # assignment-style secrets are possible in any text file, including Markdown and source.
    with path.open("rb") as fh:
        first = fh.read(SCAN_CHUNK)
        if b"\x00" in first[:8192]:
            return False
        previous = b""
        chunk = first
        while chunk:
            window = previous + chunk
            if _chunk_secret_suspect(window, structured):
                return True
            previous = window[-SCAN_OVERLAP:]
            chunk = fh.read(SCAN_CHUNK)
    return False


def sqlite_evidence(path: Path) -> dict:
    wal_path = Path(str(path) + "-wal")
    wal_bytes = wal_path.stat().st_size if wal_path.is_file() else 0
    result = {
        "checked": True,
        "integrity": "unknown",
        "table_count": None,
        "known_counts": {},
        "error_class": None,
        "wal_present": wal_bytes > 0,
        "wal_bytes": wal_bytes,
        "snapshot_required": wal_bytes > 0,
    }
    uri = "file:" + urllib.parse.quote(str(path.resolve())) + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            row = con.execute("PRAGMA integrity_check").fetchone()
            raw_integrity = row[0] if row else "no-result"
            if raw_integrity == "ok":
                result["integrity"] = "ok"
            elif "fts" in str(raw_integrity).lower() and "inverted index" in str(raw_integrity).lower():
                result["integrity"] = "warning-derived-fts-index"
                result["error_class"] = "rebuildable-fts-index"
            else:
                result["integrity"] = "error"
                result["error_class"] = "sqlite-integrity-error"
            tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            result["table_count"] = len(tables)
            for table in ("sessions", "messages"):
                if table in tables:
                    safe = '"' + table.replace('"', '""') + '"'
                    result["known_counts"][table] = int(con.execute(f"SELECT COUNT(*) FROM {safe}").fetchone()[0])
        finally:
            con.close()
    except sqlite3.DatabaseError:
        result["integrity"] = "error"
        result["error_class"] = "sqlite-database-error"
    except OSError:
        result["integrity"] = "error"
        result["error_class"] = "filesystem-error"
    return result


def build_inventory(
    root: Path,
    profile_name: str,
    include_time: bool = True,
    recovery_prefixes: tuple[str, ...] | None = None,
) -> dict:
    prefixes = resolve_recovery_prefixes() if recovery_prefixes is None else recovery_prefixes
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError("source root does not exist or is not a directory")
    if root.name == "profiles":
        raise ValueError("root must be one exact named-profile directory, not the profiles container")
    nested_named = root / "profiles" / profile_name
    if profile_name != "default" and nested_named.is_dir():
        raise ValueError("root appears to be HERMES_HOME; use the exact named-profile directory")

    files: list[dict] = []
    dbs: list[dict] = []
    errors: list[dict] = []
    for base, dirs, names in os.walk(root, topdown=True, followlinks=False):
        base_path = Path(base)
        dirs.sort()
        names.sort()
        # Keep excluded directories visible as entries only when they are symlinks;
        # do not descend into derived/recovery/cache trees.
        kept_dirs = []
        for dirname in dirs:
            p = base_path / dirname
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                files.append({
                    "relative_path": rel,
                    "type": "symlink",
                    "classification": "excluded-link",
                    "transfer_eligible": False,
                    "size": None,
                    "mode": mode_string(p, follow_symlinks=False),
                    "sha256": None,
                    "secret_suspect": False,
                })
                continue
            cls = classify_path(rel, prefixes)
            if cls.startswith("excluded-"):
                files.append({
                    "relative_path": rel + "/",
                    "type": "excluded-directory",
                    "classification": cls,
                    "transfer_eligible": False,
                    "size": None,
                    "mode": mode_string(p),
                    "sha256": None,
                    "secret_suspect": False,
                })
                continue
            kept_dirs.append(dirname)
        dirs[:] = kept_dirs

        for name in names:
            path = base_path / name
            rel = path.relative_to(root).as_posix()
            try:
                if path.is_symlink():
                    files.append({
                        "relative_path": rel,
                        "type": "symlink",
                        "classification": "excluded-link",
                        "transfer_eligible": False,
                        "size": None,
                        "mode": mode_string(path, follow_symlinks=False),
                        "sha256": None,
                        "secret_suspect": False,
                    })
                    continue
                if not path.is_file():
                    files.append({
                        "relative_path": rel,
                        "type": "unsupported",
                        "classification": "excluded-unsupported",
                        "transfer_eligible": False,
                        "size": None,
                        "mode": mode_string(path),
                        "sha256": None,
                        "secret_suspect": False,
                    })
                    continue
                cls = classify_path(rel, prefixes)
                st = path.stat()
                lower = name.lower()
                is_database = lower.endswith((".db", ".sqlite", ".sqlite3")) and cls != "excluded-secret"
                db_evidence = sqlite_evidence(path) if is_database else None
                excluded = cls.startswith("excluded-")
                digest = None if excluded else sha256_file(path)
                suspect = False if excluded else content_secret_suspect(path, st.st_size)
                snapshot_required = bool(db_evidence and db_evidence["snapshot_required"])
                transfer = not excluded and not suspect and not snapshot_required
                effective_class = "dynamic-database-live-wal" if snapshot_required else ("secret-suspect" if suspect else cls)
                entry = {
                    "relative_path": rel,
                    "type": "file",
                    "classification": effective_class,
                    "transfer_eligible": transfer,
                    "size": st.st_size,
                    "mode": f"{stat.S_IMODE(st.st_mode):04o}",
                    "sha256": digest,
                    "secret_suspect": suspect,
                    "snapshot_required": snapshot_required,
                }
                files.append(entry)
                if db_evidence is not None:
                    dbs.append({"relative_path": rel, **db_evidence})
            except (OSError, ValueError) as exc:
                errors.append({"relative_path": rel, "error_class": type(exc).__name__})

    files.sort(key=lambda x: x["relative_path"])
    dbs.sort(key=lambda x: x["relative_path"])
    class_counts: dict[str, int] = {}
    transfer_bytes = 0
    for item in files:
        class_counts[item["classification"]] = class_counts.get(item["classification"], 0) + 1
        if item["transfer_eligible"] and isinstance(item["size"], int):
            transfer_bytes += item["size"]
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    out = {
        "schema": "hermes-profile-inventory/v1",
        "profile_name": profile_name,
        "source_root": str(root),
        "read_only": True,
        "files": files,
        "databases": dbs,
        "errors": errors,
        "summary": {
            "entries": len(files),
            "transfer_eligible_files": sum(1 for x in files if x["transfer_eligible"]),
            "transfer_eligible_bytes": transfer_bytes,
            "secret_suspects": sum(1 for x in files if x["secret_suspect"]),
            "snapshot_required_databases": sum(1 for x in files if x.get("snapshot_required")),
            "excluded_links": class_counts.get("excluded-link", 0),
            "errors": len(errors),
            "class_counts": dict(sorted(class_counts.items())),
            "file_set_sha256": hashlib.sha256(canonical).hexdigest(),
        },
    }
    if include_time:
        out["generated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    return out


def write_owner_only(path: Path, payload: dict) -> None:
    path = path.expanduser()
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("output parent must be a real directory")
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(parent))
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fd = -1
            fh.write(text)
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
    ap = argparse.ArgumentParser(description="Read-only Hermes profile migration inventory")
    ap.add_argument("--root", required=True)
    ap.add_argument("--profile-name", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--fail-on-secret-suspects", action="store_true")
    ap.add_argument("--no-timestamp", action="store_true")
    ap.add_argument(
        "--recovery-prefix", action="append", default=[], metavar="PREFIX",
        help=f"extra name prefix to exclude as recovery material (repeatable; also {RECOVERY_PREFIX_ENV})",
    )
    args = ap.parse_args()
    try:
        inv = build_inventory(
            Path(args.root), args.profile_name, not args.no_timestamp,
            resolve_recovery_prefixes(args.recovery_prefix),
        )
        write_owner_only(Path(args.output), inv)
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "error_class": type(exc).__name__, "error": str(exc)[:200]}), file=sys.stderr)
        return 2
    summary = inv["summary"]
    has_hold = bool(summary["errors"] or summary["snapshot_required_databases"])
    has_secret_hold = bool(args.fail_on_secret_suspects and summary["secret_suspects"])
    print(json.dumps({"status": "HOLD" if has_hold or has_secret_hold else "PASS", "output": str(Path(args.output)), **summary}, sort_keys=True))
    if has_hold:
        return 2
    if has_secret_hold:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

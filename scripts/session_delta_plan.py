#!/usr/bin/env python3
"""Plan additive Hermes session migration without emitting transcripts."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import urllib.parse
from pathlib import Path

VISIBLE_FIELDS = (
    "role", "content", "timestamp", "tool_call_id", "tool_name", "tool_calls",
    "api_content", "display_kind", "display_metadata", "token_count",
    "finish_reason", "effect_disposition", "observed", "active", "compacted",
)
SESSION_FIELDS = (
    "model", "model_config", "system_prompt", "started_at", "ended_at", "end_reason",
    "cwd", "git_branch", "git_repo_root", "title",
)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def connect_ro(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise ValueError("database path is not a regular file")
    wal_path = Path(str(path) + "-wal")
    if wal_path.is_file() and wal_path.stat().st_size > 0:
        raise ValueError("live WAL detected; create a SQLite online-backup snapshot first")
    uri = "file:" + urllib.parse.quote(str(path.resolve())) + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def integrity(con: sqlite3.Connection) -> str:
    row = con.execute("PRAGMA integrity_check").fetchone()
    raw = row[0] if row else "no-result"
    if raw == "ok":
        return "ok"
    if "fts" in str(raw).lower() and "inverted index" in str(raw).lower():
        return "warning-derived-fts-index"
    return "error"


def columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}


def normalize(value):
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest(), "length": len(value)}
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str):
            stripped = value.strip()
            if stripped and stripped[0] in "[{":
                try:
                    return normalize(json.loads(stripped))
                except (json.JSONDecodeError, TypeError):
                    pass
        return value
    if isinstance(value, list):
        return [normalize(x) for x in value]
    if isinstance(value, dict):
        return {str(k): normalize(v) for k, v in sorted(value.items())}
    return str(value)


def fingerprint_message(row: sqlite3.Row, available: set[str], parent_ordinal: int | None) -> str:
    payload = {field: normalize(row[field]) if field in available else None for field in VISIBLE_FIELDS}
    payload["parent_ordinal"] = parent_ordinal
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def fingerprint_session_metadata(session: dict, available: set[str]) -> str:
    payload = {field: normalize(session.get(field)) if field in available else None for field in SESSION_FIELDS}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def load_db(path: Path) -> dict:
    before_sha256 = file_sha256(path)
    con = connect_ro(path)
    try:
        check = integrity(con)
        if check not in {"ok", "warning-derived-fts-index"}:
            raise ValueError("database integrity check failed")
        if con.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("database foreign-key check failed")
        session_cols = columns(con, "sessions")
        message_cols = columns(con, "messages")
        if "id" not in session_cols or not {"id", "session_id"}.issubset(message_cols):
            raise ValueError("unsupported sessions/messages schema")
        sessions = [dict(r) for r in con.execute('SELECT * FROM "sessions" ORDER BY id')]
        session_rows = {str(row["id"]): row for row in sessions}
        records: dict[str, dict] = {}
        missing_message_parents = 0
        for session in sessions:
            sid = str(session["id"])
            rows = list(con.execute('SELECT * FROM "messages" WHERE session_id=? ORDER BY "id"', (sid,)))
            ordinals = {str(r["id"]): index for index, r in enumerate(rows)}
            parent_ordinals: list[int | None] = []
            for row in rows:
                parent_ordinal = None
                if "parent_message_id" in message_cols:
                    parent = row["parent_message_id"]
                    if parent is not None:
                        parent_ordinal = ordinals.get(str(parent))
                        if parent_ordinal is None:
                            missing_message_parents += 1
                parent_ordinals.append(parent_ordinal)
            fps = [fingerprint_message(r, message_cols, parent_ordinals[index]) for index, r in enumerate(rows)]
            records[sid] = {
                "message_count": len(rows),
                "message_fingerprints": fps,
                "sequence_sha256": hashlib.sha256("\n".join(fps).encode()).hexdigest(),
                "session_metadata_sha256": fingerprint_session_metadata(session, session_cols),
            }
        missing_session_parents = 0
        for sid, record in records.items():
            parent_id = session_rows[sid].get("parent_session_id") if "parent_session_id" in session_cols else None
            parent_reference = None
            if parent_id is not None:
                parent = records.get(str(parent_id))
                if parent is None:
                    missing_session_parents += 1
                else:
                    parent_reference = {
                        "sequence_sha256": parent["sequence_sha256"],
                        "session_metadata_sha256": parent["session_metadata_sha256"],
                    }
            raw_parent_sha256 = None if parent_id is None else hashlib.sha256(str(parent_id).encode()).hexdigest()
            remap_relation_payload = {
                "session_metadata_sha256": record["session_metadata_sha256"],
                "parent_reference": parent_reference,
            }
            same_id_relation_payload = {
                "session_metadata_sha256": record["session_metadata_sha256"],
                "parent_session_id_sha256": raw_parent_sha256,
            }
            record["remap_relationship_sha256"] = hashlib.sha256(
                json.dumps(remap_relation_payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            record["same_id_relationship_sha256"] = hashlib.sha256(
                json.dumps(same_id_relation_payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        after_sha256 = file_sha256(path)
        if after_sha256 != before_sha256:
            raise ValueError("database changed during read; create a stable snapshot")
        return {
            "path": str(path.resolve()),
            "sha256": before_sha256,
            "integrity": check,
            "session_count": len(sessions),
            "message_count": sum(x["message_count"] for x in records.values()),
            "missing_message_parent_count": missing_message_parents,
            "missing_session_parent_count": missing_session_parents,
            "missing_parent_count": missing_message_parents + missing_session_parents,
            "sessions": records,
        }
    finally:
        con.close()


def safe_prefix(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw).strip("-")
    if not cleaned:
        raise ValueError("archive prefix is empty after normalization")
    return cleaned[:48]


def next_archive_id(prefix: str, sid: str, sequence_sha256: str, unavailable: set[str]) -> str:
    digest = hashlib.sha256(sid.encode()).hexdigest()[:16]
    base = f"{prefix}_{digest}"
    candidates = [base, f"{base}_{sequence_sha256[:8]}"]
    candidates.extend(f"{base}_{sequence_sha256[:8]}_{n}" for n in range(2, 100))
    for candidate in candidates:
        if candidate not in unavailable:
            unavailable.add(candidate)
            return candidate
    raise ValueError("unable to reserve collision-safe archive session id")


def classify_target_match(
    src: dict,
    target_sessions: dict[str, dict],
    same_id: str | None,
    excluded_cross_target_ids: set[str],
) -> tuple[str | None, str | None]:
    """Return (target_id, relation) without exposing transcript content."""
    sfp = src["message_fingerprints"]
    if same_id is not None:
        same_target = target_sessions[same_id]
        tfp = same_target["message_fingerprints"]
        relationship_matches = src["same_id_relationship_sha256"] == same_target["same_id_relationship_sha256"]
        if relationship_matches and sfp == tfp:
            return same_id, "exact"
        if relationship_matches and len(sfp) <= len(tfp) and tfp[:len(sfp)] == sfp:
            return same_id, "target-superset"
        if relationship_matches and tfp and len(tfp) < len(sfp) and sfp[:len(tfp)] == tfp:
            return same_id, "target-prefix"

    # Prior imports may have remapped the source session ID. Empty sessions are
    # not cross-matched because their distinct session records still matter.
    if sfp:
        exact = sorted(
            tid for tid, tgt in target_sessions.items()
            if tid != same_id
            and tid not in excluded_cross_target_ids
            and tgt["message_fingerprints"] == sfp
            and tgt["remap_relationship_sha256"] == src["remap_relationship_sha256"]
        )
        if exact:
            return exact[0], "exact-remapped"
        supersets = sorted(
            (tgt["message_count"], tid)
            for tid, tgt in target_sessions.items()
            if tid != same_id
            and tid not in excluded_cross_target_ids
            and tgt["remap_relationship_sha256"] == src["remap_relationship_sha256"]
            and len(sfp) < len(tgt["message_fingerprints"])
            and tgt["message_fingerprints"][:len(sfp)] == sfp
        )
        if supersets:
            return supersets[0][1], "target-superset-remapped"
        prefixes = sorted(
            ((tgt["message_count"], tid) for tid, tgt in target_sessions.items()
             if tid != same_id
             and tid not in excluded_cross_target_ids
             and tgt["remap_relationship_sha256"] == src["remap_relationship_sha256"]
             and tgt["message_fingerprints"]
             and len(tgt["message_fingerprints"]) < len(sfp)
             and sfp[:len(tgt["message_fingerprints"])] == tgt["message_fingerprints"]),
            reverse=True,
        )
        if prefixes:
            return prefixes[0][1], "target-prefix-remapped"
    return None, None


def build_plan(source: dict, target: dict | None, prefix: str, include_time: bool = True) -> dict:
    actions = []
    source_missing = 0
    archive_rows = 0
    target_sessions = target["sessions"] if target else {}
    blocked = source["missing_parent_count"] > 0 or bool(target and target["missing_parent_count"] > 0)
    matched_target_ids: set[str] = set()
    same_id_target_ids = set(source["sessions"]) & set(target_sessions)
    unavailable_ids = set(target_sessions) | set(source["sessions"])

    for sid, src in sorted(source["sessions"].items()):
        same_id = sid if sid in target_sessions else None
        excluded_cross_target_ids = matched_target_ids | same_id_target_ids
        matched_id, relation = classify_target_match(
            src, target_sessions, same_id, excluded_cross_target_ids
        )
        tgt = target_sessions.get(matched_id) if matched_id else target_sessions.get(sid)
        item = {
            "source_session_id": sid,
            "source_session_id_sha256": hashlib.sha256(sid.encode()).hexdigest(),
            "source_messages": src["message_count"],
            "source_sequence_sha256": src["sequence_sha256"],
            "matched_target_session_id": matched_id,
            "target_messages": 0 if tgt is None else tgt["message_count"],
            "target_sequence_sha256": None if tgt is None else tgt["sequence_sha256"],
            "unique_source_rows_not_in_target_prefix": None,
            "archive_session_id": None,
            "action": None,
            "reason": None,
        }
        if matched_id:
            matched_target_ids.add(matched_id)
        if blocked:
            item["action"] = "blocked"
            item["reason"] = "missing-parent-relationships"
        elif relation in {"exact", "exact-remapped"}:
            item["action"] = "no-op"
            item["reason"] = "exact-sequence-present" if relation == "exact" else "exact-sequence-present-under-remapped-id"
            item["unique_source_rows_not_in_target_prefix"] = 0
        elif relation in {"target-superset", "target-superset-remapped"}:
            item["action"] = "no-op"
            item["reason"] = "target-superset-preserves-source" if relation == "target-superset" else "remapped-target-superset-preserves-source"
            item["unique_source_rows_not_in_target_prefix"] = 0
        elif relation in {"target-prefix", "target-prefix-remapped"}:
            missing = src["message_count"] - tgt["message_count"]
            item["action"] = "archive-copy"
            item["reason"] = "target-is-source-prefix" if relation == "target-prefix" else "remapped-target-is-source-prefix"
            item["unique_source_rows_not_in_target_prefix"] = missing
            item["archive_session_id"] = next_archive_id(prefix, sid, src["sequence_sha256"], unavailable_ids)
            source_missing += missing
            archive_rows += src["message_count"]
        elif same_id is not None:
            item["action"] = "archive-copy"
            item["reason"] = "divergent-sequence-preserve-both"
            item["unique_source_rows_not_in_target_prefix"] = src["message_count"]
            item["archive_session_id"] = next_archive_id(prefix, sid, src["sequence_sha256"], unavailable_ids)
            source_missing += src["message_count"]
            archive_rows += src["message_count"]
        else:
            item["action"] = "import-new"
            item["reason"] = "source-id-and-sequence-absent-on-target"
            item["unique_source_rows_not_in_target_prefix"] = src["message_count"]
            source_missing += src["message_count"]
        actions.append(item)

    target_only = sorted(set(target_sessions) - set(source["sessions"]) - matched_target_ids)
    summary = {
        "source_sessions": source["session_count"],
        "source_messages": source["message_count"],
        "target_sessions": 0 if target is None else target["session_count"],
        "target_messages": 0 if target is None else target["message_count"],
        "actions": len(actions),
        "no_op": sum(1 for x in actions if x["action"] == "no-op"),
        "import_new": sum(1 for x in actions if x["action"] == "import-new"),
        "archive_copy": sum(1 for x in actions if x["action"] == "archive-copy"),
        "blocked": sum(1 for x in actions if x["action"] == "blocked"),
        "remapped_matches": sum(1 for x in actions if x["matched_target_session_id"] not in {None, x["source_session_id"]}),
        "target_only_sessions": len(target_only),
        "unique_source_rows_not_in_target_prefix": source_missing,
        "planned_archive_rows": archive_rows,
    }
    out = {
        "schema": "hermes-session-delta-plan/v1",
        "read_only": True,
        "contains_message_bodies": False,
        "archive_prefix": prefix,
        "source": {k: v for k, v in source.items() if k != "sessions"},
        "target": None if target is None else {k: v for k, v in target.items() if k != "sessions"},
        "actions": actions,
        "target_only_session_ids": target_only,
        "summary": summary,
    }
    canonical = json.dumps({"actions": actions, "target_only": target_only}, sort_keys=True, separators=(",", ":")).encode()
    out["plan_sha256"] = hashlib.sha256(canonical).hexdigest()
    if include_time:
        out["generated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    return out


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
    ap = argparse.ArgumentParser(description="Plan collision-safe Hermes session migration")
    ap.add_argument("--source-db", required=True)
    ap.add_argument("--target-db")
    ap.add_argument("--output", required=True)
    ap.add_argument("--archive-prefix", default="migrated-archive")
    ap.add_argument("--no-timestamp", action="store_true")
    args = ap.parse_args()
    try:
        source = load_db(Path(args.source_db))
        target = load_db(Path(args.target_db)) if args.target_db else None
        plan = build_plan(source, target, safe_prefix(args.archive_prefix), not args.no_timestamp)
        write_owner_only(Path(args.output), plan)
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "error_class": type(exc).__name__}), file=sys.stderr)
        return 2
    status = "HOLD" if plan["summary"]["blocked"] else "PASS"
    print(json.dumps({"status": status, "output": str(Path(args.output)), **plan["summary"]}, sort_keys=True))
    return 2 if status == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())

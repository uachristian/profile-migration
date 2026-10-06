#!/usr/bin/env python3
"""Synthetic verification for hermes-profile-migration helper scripts."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
INV = HERE / "profile_inventory.py"
DELTA = HERE / "session_delta_plan.py"
VERIFY = HERE / "verify_manifest.py"


def run(args, expected=(0,)):
    cp = subprocess.run([sys.executable, *map(str, args)], text=True, capture_output=True)
    if cp.returncode not in expected:
        raise AssertionError(f"command failed rc={cp.returncode}: {cp.stderr[:500]}")
    return cp


def make_db(path: Path, sessions: dict[str, list[str]], session_parents: dict[str, str] | None = None) -> None:
    con = sqlite3.connect(path)
    con.executescript("""
      CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT, source TEXT, parent_session_id TEXT);
      CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT,
        timestamp REAL,
        parent_message_id INTEGER,
        tool_call_id TEXT,
        tool_name TEXT,
        tool_calls TEXT,
        api_content TEXT,
        display_kind TEXT,
        display_metadata TEXT,
        token_count INTEGER,
        finish_reason TEXT,
        observed INTEGER
      );
    """)
    for sid, bodies in sessions.items():
        ts = 1.0
        parent_session_id = (session_parents or {}).get(sid)
        con.execute(
            "INSERT INTO sessions(id,title,source,parent_session_id) VALUES(?,?,?,?)",
            (sid, "synthetic", "cli", parent_session_id),
        )
        parent = None
        for index, body in enumerate(bodies):
            cur = con.execute(
                "INSERT INTO messages(session_id,role,content,timestamp,parent_message_id,observed) VALUES(?,?,?,?,?,?)",
                (sid, "user" if index % 2 == 0 else "assistant", body, ts, parent, 1),
            )
            parent = cur.lastrowid
            ts += 1
    con.commit()
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    con.close()


def main() -> int:
    assert sys.version_info >= (3, 11)
    with tempfile.TemporaryDirectory(prefix="hermes-migration-tools-") as td:
        root = Path(td)
        profile = root / "profile"
        (profile / "workspace").mkdir(parents=True)
        (profile / "logs").mkdir()
        (profile / "node_modules").mkdir()
        (profile / "SOUL.md").write_text("Synthetic migration profile.\n")
        (profile / "workspace" / "project.txt").write_text("project data\n")
        (profile / "config.yaml").write_text("gateway:\n  platforms: {}\nkey_ref: ${TOKEN}\n")
        (profile / ".env").write_text("SYNTHETIC_ONLY=1\n")
        (profile / "auth.json").write_text("{}\n")
        (profile / "logs" / "gateway.log").write_text("synthetic log\n")
        (profile / "node_modules" / "ignored.js").write_text("ignored\n")
        suspect_value = "unit-value-" + "x" * 24
        (profile / "workspace" / "suspect.yaml").write_text("SERVICE_TOKEN=" + suspect_value + "\n")
        (profile / "workspace" / "secret-notes.md").write_text("SERVICE_TOKEN=" + "unit-value-" + "m" * 24 + "\n")
        (profile / ".npmrc").write_text("registry=https://invalid.example\n")
        (profile / "workspace" / "quoted-secret.json").write_text(
            json.dumps({"access_token": "unit-value-" + "y" * 24}) + "\n"
        )
        oversized = profile / "workspace" / "oversized-secret.yaml"
        with oversized.open("w") as fh:
            fh.write("safe_key: safe_value\n" * 120000)
            fh.write("SERVICE_TOKEN: " + "unit-value-" + "z" * 24 + "\n")
        try:
            os.symlink("project.txt", profile / "workspace" / "link.txt")
        except OSError:
            pass
        make_db(profile / "state.db", {"exact": ["a", "b"], "prefix": ["a", "b", "c"], "diverge": ["left"]})

        inventory_path = root / "inventory.json"
        run([INV, "--root", profile, "--profile-name", "synthetic", "--output", inventory_path, "--fail-on-secret-suspects", "--no-timestamp"], expected=(3,))
        inv = json.loads(inventory_path.read_text())
        by_path = {x["relative_path"]: x for x in inv["files"]}
        assert by_path[".env"]["classification"] == "excluded-secret"
        assert by_path["auth.json"]["classification"] == "excluded-secret"
        assert by_path["workspace/project.txt"]["transfer_eligible"] is True
        assert by_path["workspace/suspect.yaml"]["classification"] == "secret-suspect"
        assert by_path["workspace/secret-notes.md"]["classification"] == "secret-suspect"
        assert by_path["workspace/secret-notes.md"]["transfer_eligible"] is False
        assert by_path[".npmrc"]["classification"] == "excluded-secret"
        assert by_path["workspace/quoted-secret.json"]["classification"] == "secret-suspect"
        assert by_path["workspace/oversized-secret.yaml"]["classification"] == "secret-suspect"
        assert by_path["workspace/quoted-secret.json"]["transfer_eligible"] is False
        assert by_path["workspace/oversized-secret.yaml"]["transfer_eligible"] is False
        assert any(x["classification"] == "excluded-derived" for x in inv["files"])
        if "workspace/link.txt" in by_path:
            assert by_path["workspace/link.txt"]["classification"] == "excluded-link"
        state_db = next(x for x in inv["databases"] if x["relative_path"] == "state.db")
        assert state_db["integrity"] == "ok"
        assert state_db["known_counts"] == {"messages": 6, "sessions": 3}
        assert oct(inventory_path.stat().st_mode & 0o777) == "0o600"

        # Default-root inventory must never absorb unrelated named profiles.
        hermes_home = root / "hermes-home"
        (hermes_home / "profiles" / "a").mkdir(parents=True)
        (hermes_home / "profiles" / "b").mkdir(parents=True)
        (hermes_home / "profiles" / "a" / "SOUL.md").write_text("a\n")
        (hermes_home / "profiles" / "b" / "SOUL.md").write_text("b\n")
        default_inventory = root / "default-inventory.json"
        run([INV, "--root", hermes_home, "--profile-name", "default", "--output", default_inventory, "--no-timestamp"])
        default_payload = json.loads(default_inventory.read_text())
        assert any(x["relative_path"] == "profiles/" and x["classification"] == "excluded-sibling-profiles" for x in default_payload["files"])
        assert not any(x.get("relative_path", "").startswith("profiles/a/") for x in default_payload["files"])
        run([INV, "--root", hermes_home, "--profile-name", "a", "--output", root / "wrong-root.json", "--no-timestamp"], expected=(2,))

        # Atomic output replacement must replace a stale symlink, not its target.
        victim = root / "victim.txt"
        victim.write_text("safe\n")
        redirect = root / "redirect.json"
        try:
            os.symlink(victim.name, redirect)
            run([INV, "--root", profile, "--profile-name", "synthetic", "--output", redirect, "--no-timestamp"])
            assert victim.read_text() == "safe\n"
            assert not redirect.is_symlink()
            assert json.loads(redirect.read_text())["schema"] == "hermes-profile-inventory/v1"
        except OSError:
            pass

        verify_unresolved = root / "verify-unresolved.json"
        run([VERIFY, "--root", profile, "--manifest", inventory_path, "--output", verify_unresolved, "--no-timestamp"], expected=(1,))
        assert any(x["failure"] == "source-secret-suspects-unresolved" for x in json.loads(verify_unresolved.read_text())["failures"])
        verify_ok = root / "verify-ok.json"
        run([
            VERIFY, "--root", profile, "--manifest", inventory_path,
            "--allow-excluded-secret-suspects", "--output", verify_ok, "--no-timestamp",
        ])
        assert json.loads(verify_ok.read_text())["status"] == "PASS"
        original_soul_mode = profile.joinpath("SOUL.md").stat().st_mode & 0o777
        os.chmod(profile / "SOUL.md", 0o600 if original_soul_mode != 0o600 else 0o644)
        verify_mode = root / "verify-mode.json"
        run([VERIFY, "--root", profile, "--manifest", inventory_path, "--allow-excluded-secret-suspects", "--output", verify_mode, "--no-timestamp"], expected=(1,))
        assert any(x["failure"] == "mode-mismatch" for x in json.loads(verify_mode.read_text())["failures"])
        os.chmod(profile / "SOUL.md", original_soul_mode)
        empty_manifest = root / "empty-manifest.json"
        empty_files: list[dict] = []
        empty_manifest.write_text(json.dumps({
            "schema": "hermes-profile-inventory/v1",
            "profile_name": "synthetic",
            "source_root": str(profile),
            "files": empty_files,
            "summary": {"file_set_sha256": hashlib.sha256(json.dumps(empty_files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()},
        }))
        verify_empty = root / "verify-empty.json"
        run([VERIFY, "--root", profile, "--manifest", empty_manifest, "--output", verify_empty, "--no-timestamp"], expected=(1,))
        assert any(x["failure"] == "empty-transfer-set" for x in json.loads(verify_empty.read_text())["failures"])
        verify_unknown_class = root / "verify-unknown-class.json"
        run([
            VERIFY, "--root", profile, "--manifest", inventory_path,
            "--classes", "substantiv-typo", "--allow-excluded-secret-suspects",
            "--output", verify_unknown_class, "--no-timestamp",
        ], expected=(1,))
        assert any(x["failure"] == "unknown-class-selection" for x in json.loads(verify_unknown_class.read_text())["failures"])
        tampered_manifest = root / "tampered-manifest.json"
        tampered_payload = json.loads(inventory_path.read_text())
        tampered_payload["summary"]["file_set_sha256"] = "0" * 64
        tampered_manifest.write_text(json.dumps(tampered_payload))
        run([
            VERIFY, "--root", profile, "--manifest", tampered_manifest,
            "--output", root / "tampered-result.json", "--no-timestamp",
        ], expected=(2,))
        (profile / "workspace" / "project.txt").write_text("changed\n")
        verify_bad = root / "verify-bad.json"
        run([VERIFY, "--root", profile, "--manifest", inventory_path, "--allow-excluded-secret-suspects", "--output", verify_bad, "--no-timestamp"], expected=(1,))
        bad = json.loads(verify_bad.read_text())
        assert bad["status"] == "FAIL"
        assert any(x["failure"] in {"size-mismatch", "hash-mismatch"} for x in bad["failures"])
        duplicate_manifest = root / "inventory-duplicate.json"
        duplicate_payload = json.loads(inventory_path.read_text())
        duplicate_entry = next(x for x in duplicate_payload["files"] if x.get("transfer_eligible"))
        duplicate_payload["files"].append(dict(duplicate_entry))
        duplicate_payload["summary"]["file_set_sha256"] = hashlib.sha256(
            json.dumps(duplicate_payload["files"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        duplicate_manifest.write_text(json.dumps(duplicate_payload))
        verify_duplicate = root / "verify-duplicate.json"
        run([VERIFY, "--root", profile, "--manifest", duplicate_manifest, "--allow-excluded-secret-suspects", "--output", verify_duplicate, "--no-timestamp"], expected=(1,))
        duplicate_result = json.loads(verify_duplicate.read_text())
        assert any(x["failure"] == "duplicate-manifest-path" for x in duplicate_result["failures"])

        # Live WAL content must be visible to inventory but never planned as a stable transfer.
        live_db = root / "live.db"
        make_db(live_db, {"committed-main": ["one"]})
        live_con = sqlite3.connect(live_db)
        assert live_con.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        live_con.execute("INSERT INTO sessions(id,title,source,parent_session_id) VALUES(?,?,?,?)", ("committed-wal", "synthetic", "cli", None))
        live_con.execute("INSERT INTO messages(session_id,role,content,timestamp,parent_message_id,observed) VALUES(?,?,?,?,?,?)", ("committed-wal", "user", "two", 1.0, None, 1))
        live_con.commit()
        assert Path(str(live_db) + "-wal").stat().st_size > 0
        live_root = root / "live-profile"
        live_root.mkdir()
        live_copy = live_root / "state.db"
        os.link(live_db, live_copy)
        os.link(Path(str(live_db) + "-wal"), Path(str(live_copy) + "-wal"))
        shm_source = Path(str(live_db) + "-shm")
        if shm_source.exists():
            os.link(shm_source, Path(str(live_copy) + "-shm"))
        live_inventory_path = root / "live-inventory.json"
        run([INV, "--root", live_root, "--profile-name", "live", "--output", live_inventory_path, "--no-timestamp"], expected=(2,))
        live_inventory = json.loads(live_inventory_path.read_text())
        live_evidence = next(x for x in live_inventory["databases"] if x["relative_path"] == "state.db")
        live_entry = next(x for x in live_inventory["files"] if x["relative_path"] == "state.db")
        assert live_evidence["known_counts"]["sessions"] == 2
        assert live_evidence["snapshot_required"] is True
        assert live_entry["transfer_eligible"] is False
        assert live_entry["classification"] == "dynamic-database-live-wal"
        run([DELTA, "--source-db", live_copy, "--output", root / "live-plan.json", "--no-timestamp"], expected=(2,))
        live_con.close()

        source_db = root / "source.db"
        target_db = root / "target.db"
        existing_archive = "synthetic_" + hashlib.sha256(b"remapped-prefix").hexdigest()[:16]
        make_db(source_db, {
            "exact": ["a", "b"],
            "prefix": ["a", "b", "c"],
            "diverge": ["left"],
            "new": ["new"],
            "remapped-exact": ["r-a", "r-b"],
            "remapped-prefix": ["p-a", "p-b", "p-c"],
        })
        make_db(target_db, {
            "exact": ["a", "b"],
            "prefix": ["a", "b"],
            "diverge": ["right"],
            "target-only": ["target"],
            "archive-old-exact": ["r-a", "r-b"],
            existing_archive: ["p-a", "p-b"],
        })
        plan_path = root / "plan.json"
        run([DELTA, "--source-db", source_db, "--target-db", target_db, "--archive-prefix", "synthetic", "--output", plan_path, "--no-timestamp"])
        plan = json.loads(plan_path.read_text())
        actions = {x["source_session_id"]: x for x in plan["actions"]}
        assert actions["exact"]["action"] == "no-op"
        assert actions["prefix"]["action"] == "archive-copy"
        assert actions["prefix"]["unique_source_rows_not_in_target_prefix"] == 1
        assert actions["diverge"]["action"] == "archive-copy"
        assert actions["new"]["action"] == "import-new"
        assert actions["remapped-exact"]["action"] == "no-op"
        assert actions["remapped-exact"]["reason"] == "exact-sequence-present-under-remapped-id"
        assert actions["remapped-prefix"]["action"] == "archive-copy"
        assert actions["remapped-prefix"]["reason"] == "remapped-target-is-source-prefix"
        assert actions["remapped-prefix"]["unique_source_rows_not_in_target_prefix"] == 1
        assert actions["remapped-prefix"]["archive_session_id"] != existing_archive
        assert plan["summary"]["remapped_matches"] == 2
        assert plan["summary"]["target_only_sessions"] == 1

        # Same visible messages with different parent graph must not be no-op.
        parent_source = root / "parent-source.db"
        parent_target = root / "parent-target.db"
        make_db(parent_source, {"thread": ["parent", "child"]})
        make_db(parent_target, {"thread": ["parent", "child"]})
        con = sqlite3.connect(parent_target)
        con.execute("UPDATE messages SET parent_message_id=NULL WHERE id=(SELECT MAX(id) FROM messages)")
        con.commit()
        con.close()
        parent_plan_path = root / "parent-plan.json"
        run([DELTA, "--source-db", parent_source, "--target-db", parent_target, "--archive-prefix", "parent-test", "--output", parent_plan_path, "--no-timestamp"])
        parent_plan = json.loads(parent_plan_path.read_text())
        assert parent_plan["actions"][0]["action"] == "archive-copy"
        assert parent_plan["actions"][0]["reason"] == "divergent-sequence-preserve-both"

        session_parent_source = root / "session-parent-source.db"
        session_parent_target = root / "session-parent-target.db"
        relationship_sessions = {"parent-a": ["identical-parent"], "parent-b": ["identical-parent"], "child": ["same-child"]}
        make_db(session_parent_source, relationship_sessions, {"child": "parent-a"})
        make_db(session_parent_target, relationship_sessions, {"child": "parent-b"})
        session_parent_plan_path = root / "session-parent-plan.json"
        run([
            DELTA, "--source-db", session_parent_source, "--target-db", session_parent_target,
            "--archive-prefix", "session-parent-test", "--output", session_parent_plan_path, "--no-timestamp",
        ])
        session_parent_actions = {x["source_session_id"]: x for x in json.loads(session_parent_plan_path.read_text())["actions"]}
        assert session_parent_actions["child"]["action"] == "archive-copy"
        assert session_parent_actions["child"]["reason"] == "divergent-sequence-preserve-both"

        # Planned archive IDs must not collide with any source session ID.
        collision_source = root / "collision-source.db"
        collision_target = root / "collision-target.db"
        collision_origin = "conflict"
        colliding_source_id = "zzz_" + hashlib.sha256(collision_origin.encode()).hexdigest()[:16]
        make_db(collision_source, {collision_origin: ["source"], colliding_source_id: ["other-source"]})
        make_db(collision_target, {collision_origin: ["target"]})
        collision_plan_path = root / "collision-plan.json"
        run([
            DELTA, "--source-db", collision_source, "--target-db", collision_target,
            "--archive-prefix", "zzz", "--output", collision_plan_path, "--no-timestamp",
        ])
        collision_actions = {x["source_session_id"]: x for x in json.loads(collision_plan_path.read_text())["actions"]}
        assert collision_actions[collision_origin]["archive_session_id"] != colliding_source_id
        assert collision_actions[colliding_source_id]["action"] == "import-new"

        # One remapped target session may represent only one distinct source session.
        duplicate_source_db = root / "duplicate-source.db"
        duplicate_target_db = root / "duplicate-target.db"
        make_db(duplicate_source_db, {"duplicate-a": ["identical"], "duplicate-b": ["identical"]})
        make_db(duplicate_target_db, {"remapped-only": ["identical"]})
        duplicate_session_plan_path = root / "duplicate-session-plan.json"
        run([
            DELTA, "--source-db", duplicate_source_db, "--target-db", duplicate_target_db,
            "--archive-prefix", "duplicate-test", "--output", duplicate_session_plan_path, "--no-timestamp",
        ])
        duplicate_session_plan = json.loads(duplicate_session_plan_path.read_text())
        duplicate_actions = {x["source_session_id"]: x for x in duplicate_session_plan["actions"]}
        assert sorted(x["action"] for x in duplicate_actions.values()) == ["import-new", "no-op"]
        assert duplicate_session_plan["summary"]["import_new"] == 1
        assert duplicate_session_plan["summary"]["no_op"] == 1
        assert duplicate_session_plan["summary"]["unique_source_rows_not_in_target_prefix"] == 1

        assert plan["contains_message_bodies"] is False
        raw_plan = plan_path.read_text()
        assert "right" not in raw_plan and '"content"' not in raw_plan
        assert oct(plan_path.stat().st_mode & 0o777) == "0o600"

    print(json.dumps({"status": "PASS", "checks": 66, "production_mutations": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

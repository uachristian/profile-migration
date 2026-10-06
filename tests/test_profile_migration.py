"""Stdlib unittest: inventory, secret scan, and manifest verification on a synthetic profile.

Every fixture is built at test time inside a temporary directory. Planted secret-like
values are assembled by concatenation so no literal credential-shaped string exists
in this source file.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
INVENTORY = SCRIPTS / "profile_inventory.py"
VERIFY = SCRIPTS / "verify_manifest.py"
DELTA = SCRIPTS / "session_delta_plan.py"


def run(*args: object) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, *map(str, args)], text=True, capture_output=True, env=env)


def planted_value(fill: str) -> str:
    return "synthetic" + "-" + "value-" + fill * 24


class ProfileMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(prefix="profile-migration-test-")
        self.tmp = Path(self._td.name)
        self.home = self.tmp / "hermes-home"
        self.profile = self.home / "profiles" / "alpha"
        sibling = self.home / "profiles" / "beta"
        (self.profile / "skills" / "demo").mkdir(parents=True)
        (self.profile / "memories").mkdir()
        (self.profile / "logs").mkdir()
        sibling.mkdir(parents=True)
        (sibling / "SOUL.md").write_text("sibling persona\n")
        (self.profile / "SOUL.md").write_text("Synthetic persona.\n")
        (self.profile / "skills" / "demo" / "SKILL.md").write_text("---\nname: demo\n---\n")
        (self.profile / "memories" / "MEMORY.md").write_text("synthetic memory\n")
        (self.profile / "config.yaml").write_text("model: synthetic\nkey_ref: ${SERVICE_KEY}\n")
        (self.profile / "logs" / "agent.log").write_text("runtime noise\n")
        self.env_value = planted_value("e")
        (self.profile / ".env").write_text("BOT_" + "TOKEN=" + self.env_value + "\n")
        self.notes_value = planted_value("n")
        (self.profile / "memories" / "notes.md").write_text("API_" + "KEY: " + self.notes_value + "\n")
        con = sqlite3.connect(self.profile / "state.db")
        con.executescript(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT, source TEXT, parent_session_id TEXT);"
            "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT,"
            " content TEXT, timestamp REAL, parent_message_id INTEGER);"
        )
        con.execute("INSERT INTO sessions VALUES ('s1','t','cli',NULL)")
        con.execute("INSERT INTO messages(session_id,role,content,timestamp) VALUES ('s1','user','hi',1.0)")
        con.commit()
        con.close()
        self.inventory = self.tmp / "out" / "inventory.json"

    def tearDown(self) -> None:
        self._td.cleanup()

    def build_inventory(self, *extra: str) -> tuple[subprocess.CompletedProcess, dict]:
        cp = run(INVENTORY, "--root", self.profile, "--profile-name", "alpha",
                 "--output", self.inventory, "--no-timestamp", *extra)
        return cp, json.loads(self.inventory.read_text())

    def test_inventory_classifies_and_excludes(self) -> None:
        cp, inv = self.build_inventory()
        self.assertEqual(cp.returncode, 0, cp.stderr)
        files = {f["relative_path"]: f for f in inv["files"]}
        self.assertTrue(files["SOUL.md"]["transfer_eligible"])
        self.assertTrue(files["skills/demo/SKILL.md"]["transfer_eligible"])
        self.assertEqual(files[".env"]["classification"], "excluded-secret")
        self.assertFalse(files[".env"]["transfer_eligible"])
        self.assertFalse(any(p.startswith("logs/") and files[p]["transfer_eligible"] for p in files))
        self.assertEqual(self.inventory.stat().st_mode & 0o777, 0o600)

    def test_recovery_prefixes_default_and_configurable(self) -> None:
        for name in ("backup-2026", "site-drill"):
            (self.profile / name).mkdir()
            (self.profile / name / "SOUL.md").write_text("old copy\n")
        cp, inv = self.build_inventory()
        self.assertEqual(cp.returncode, 0, cp.stderr)
        files = {f["relative_path"]: f for f in inv["files"]}
        self.assertEqual(files["backup-2026/"]["classification"], "excluded-recovery")
        self.assertTrue(files["site-drill/SOUL.md"]["transfer_eligible"])
        cp, inv = self.build_inventory("--recovery-prefix", "site-drill")
        files = {f["relative_path"]: f for f in inv["files"]}
        self.assertEqual(files["site-drill/"]["classification"], "excluded-recovery")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PROFILE_MIGRATION_RECOVERY_PREFIXES="site-")
        subprocess.run([sys.executable, str(INVENTORY), "--root", str(self.profile), "--profile-name", "alpha",
                        "--output", str(self.inventory), "--no-timestamp"], env=env, capture_output=True, check=True)
        files = {f["relative_path"]: f for f in json.loads(self.inventory.read_text())["files"]}
        self.assertEqual(files["site-drill/"]["classification"], "excluded-recovery")

    def test_exact_profile_root_required(self) -> None:
        cp = run(INVENTORY, "--root", self.home, "--profile-name", "alpha",
                 "--output", self.inventory, "--no-timestamp")
        self.assertEqual(cp.returncode, 2)
        cp = run(INVENTORY, "--root", self.home / "profiles", "--profile-name", "alpha",
                 "--output", self.inventory, "--no-timestamp")
        self.assertEqual(cp.returncode, 2)

    def test_default_root_excludes_sibling_profiles(self) -> None:
        out = self.tmp / "default.json"
        cp = run(INVENTORY, "--root", self.home, "--profile-name", "default", "--output", out, "--no-timestamp")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        paths = [f["relative_path"] for f in json.loads(out.read_text())["files"]]
        self.assertIn("profiles/", paths)
        self.assertFalse(any(p.startswith("profiles/alpha/") or p.startswith("profiles/beta/") for p in paths))

    def test_secret_scan_flags_without_printing_values(self) -> None:
        cp, inv = self.build_inventory("--fail-on-secret-suspects")
        self.assertEqual(cp.returncode, 3)
        files = {f["relative_path"]: f for f in inv["files"]}
        self.assertEqual(files["memories/notes.md"]["classification"], "secret-suspect")
        self.assertFalse(files["memories/notes.md"]["transfer_eligible"])
        self.assertTrue(files["config.yaml"]["transfer_eligible"])  # ${REF} is not a value
        blob = self.inventory.read_text() + cp.stdout + cp.stderr
        for value in (self.env_value, self.notes_value):
            self.assertNotIn(value, blob)

    def test_manifest_verify_pass_and_tamper(self) -> None:
        self.build_inventory()
        report = self.tmp / "verify.json"
        cp = run(VERIFY, "--root", self.profile, "--manifest", self.inventory,
                 "--allow-excluded-secret-suspects", "--output", report, "--no-timestamp")
        self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
        self.assertEqual(json.loads(report.read_text())["status"], "PASS")
        cp = run(VERIFY, "--root", self.profile, "--manifest", self.inventory,
                 "--output", report, "--no-timestamp")
        self.assertEqual(cp.returncode, 1)
        (self.profile / "SOUL.md").write_text("tampered\n")
        cp = run(VERIFY, "--root", self.profile, "--manifest", self.inventory,
                 "--allow-excluded-secret-suspects", "--output", report, "--no-timestamp")
        self.assertEqual(cp.returncode, 1)
        failures = {f["failure"] for f in json.loads(report.read_text())["failures"]}
        self.assertTrue(failures & {"size-mismatch", "hash-mismatch"})

    def test_live_wal_database_is_held(self) -> None:
        con = sqlite3.connect(self.profile / "state.db")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("INSERT INTO sessions VALUES ('s2','t','cli',NULL)")
        con.commit()
        try:
            cp, inv = self.build_inventory()
            self.assertEqual(cp.returncode, 2)
            entry = next(f for f in inv["files"] if f["relative_path"] == "state.db")
            self.assertFalse(entry["transfer_eligible"])
            cp = run(DELTA, "--source-db", self.profile / "state.db",
                     "--output", self.tmp / "plan.json", "--no-timestamp")
            self.assertEqual(cp.returncode, 2)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()

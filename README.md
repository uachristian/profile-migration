# Hermes Profile Migration

A fail-closed [Hermes Agent](https://hermes-agent.nousresearch.com/docs) skill plus stdlib-only helper
scripts for moving a Hermes profile between **local**, **Docker**, and **managed Cloud** runtimes
without leaking credentials, clobbering live history, or running one bot in two places.

## What it covers

| Direction | Typical path |
|---|---|
| local ↔ Docker | inventory the exact profile root (host dir or mounted volume), build a sanitized manifest-bound package, apply into the other `HERMES_HOME`, verify hashes/modes |
| local/Docker → managed Cloud | local stays authoritative; Cloud target stays production-disabled while files and history import additively; separate cutover |
| managed Cloud → local/Docker | download and audit a full Cloud backup, restore into a sibling disposable root, verify, then cut over |
| Cloud → Cloud | sanitized intermediate package only — never shared credentials |

Three modes are kept separate: **A** portable `hermes profile export/import`, **B** full-state
migration, **C** production cutover (credentials and channels). See `SKILL.md` and
`references/migration-mode-matrix.md`.

## Safety model

- **Exact-profile-root inventory.** `--root` must be one named-profile directory; pointing at the Hermes
  home or the `profiles/` container fails. A default-profile inventory excludes the `profiles/`
  subtree so sibling profiles never enter the package.
- **Secret-assignment scanning without printing values.** Every text/config file is scanned in full
  (chunked, including large files and quoted JSON keys). Hits are reported by path only.
- **Credential/runtime/cache exclusions.** `.env`, `auth.json`, keys, cookies, logs, locks, PIDs,
  caches, dependency trees, `.git`, backup and recovery trees are never transfer-eligible.
- **Stable SQLite snapshots.** Databases are opened read-only. A non-empty WAL sidecar is a HOLD:
  take an online-backup snapshot first.
- **Additive, collision-safe session history.** The delta planner never replaces a target
  `state.db`; divergent sessions become deterministic archival copies, and the plan contains no
  message bodies.
- **Manifest verification.** Target files are checked against the inventory by path, size,
  SHA-256 and mode; tampered manifests, duplicates and empty transfer sets fail.
- **Single poller.** Never run the same bot token in two places. The source poller is stopped and
  proven stopped before the target is given the credential.
- **The operator enters credentials themselves.** Nothing in this repo transfers, prints or stores a
  secret. On cutover, you type the token into the target's own config/secret store; the agent only
  verifies that the channel connected.

The helpers are read-only planners/verifiers. Cloud writes, restarts, credential entry and cutover
are performed by you through the destination's supported interface after explicit approval.

## Layout

```
SKILL.md                           the skill (procedure, invariants, pitfalls)
references/migration-mode-matrix.md
scripts/profile_inventory.py       read-only inventory + secret/runtime classification
scripts/session_delta_plan.py      transcript-free additive history planner
scripts/verify_manifest.py         target hash/mode verification against an inventory
scripts/verify_tools.py            synthetic end-to-end regression suite
scripts/verify_source_manifest.py  verify/regenerate SOURCE_MANIFEST.json
templates/                         contract, backup, cutover, rollback, completion receipts
tests/test_profile_migration.py    stdlib unittest on a synthetic profile
```

## Install as a skill

```bash
dest="$HOME/.hermes/skills/devops/hermes-profile-migration"
mkdir -p "$dest"
rsync -a --exclude .git --exclude .github --exclude tests --exclude README.md \
  --exclude LICENSE --exclude SOURCE_MANIFEST.json --exclude scripts/verify_source_manifest.py \
  ./ "$dest/"
```

For a Docker-hosted Hermes, copy into the mounted `HERMES_HOME` volume's `skills/` directory instead.
For managed Cloud, upload the skill through the provider's supported skill/file interface.

## Quick use

```bash
python3 scripts/profile_inventory.py --root <exact-profile-root> --profile-name <name> \
  --output <job>/01-source-inventory.json --fail-on-secret-suspects
python3 scripts/session_delta_plan.py --source-db <source-snapshot.db> --target-db <target-snapshot.db> \
  --output <job>/06-session-delta-plan.json
python3 scripts/verify_manifest.py --root <restored-target-root> --manifest <job>/01-source-inventory.json \
  --output <job>/08-parity.json
```

Keep job outputs out of this repository; they contain machine paths and private-file hashes.

## Verification

Requires Python 3.11+ (stdlib only). The system `python3` on some hosts (for example macOS) is older; check with `python3 --version` and use an explicit interpreter such as `python3.12` if needed.

Recovery folders (names starting with `backup`, `recovery`, `snapshot`, `restore`, `rollback`, plus folders such as `backups/` and `checkpoints/`) are excluded from transfer. Add site-specific prefixes with `--recovery-prefix <prefix>` (repeatable) or `PROFILE_MIGRATION_RECOVERY_PREFIXES=prefix1,prefix2`.

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 scripts/verify_tools.py
python3 -m unittest discover -s tests -v
python3 scripts/verify_source_manifest.py           # --write to regenerate after edits
```

All tests build synthetic profiles in temporary directories and never touch a real Hermes home.
`SOURCE_MANIFEST.json` pins the size and SHA-256 of every tracked source file so a reviewer can
confirm the tree matches what was published.

## License

MIT — see `LICENSE`.

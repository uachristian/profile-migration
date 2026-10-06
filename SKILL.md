---
name: hermes-profile-migration
description: Use when migrating Hermes profiles to or from Cloud.
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, profiles, migration, cloud, docker, backup]
    related_skills: [hermes-agent]
---

# Hermes Profile Migration

## Overview

Use this skill to move a Hermes profile safely between local Hermes, a fully Dockerized profile, and a managed Cloud agent—including Cloud-to-Cloud and Cloud-to-local moves.

Always separate:

1. **Portable profile transfer** — persona, configuration, memories, skills, sessions, and profile-local files through supported `hermes profile export/import`.
2. **Full-state migration** — external projects, source authority, databases, vaults, scripts, complete history, and data outside a named profile directory.
3. **Production cutover** — credentials, channel ownership, cron, connectors, callbacks, webhooks, and external-write authority.

A profile is not migrated merely because it starts or replies. Completion requires separate operational-readiness and data-completeness verdicts.

Load `hermes-agent` for current CLI behavior and treat the official Hermes documentation as authoritative. Use your managed-Cloud operating procedure for Dashboard/API work, your backup procedure for rollback artifacts, your change-control procedure before production mutations, and your Docker procedure when either endpoint is containerized.

## When to Use

- Moving local/Docker Hermes to managed Cloud.
- Bringing a Cloud profile back to local/Docker.
- Moving a profile between Cloud agents.
- Cloning or recovering a profile with useful history and project state.
- Deciding whether supported profile export/import is sufficient.
- Turning a one-off migration into a repeatable procedure.

Do not treat this skill as approval to transfer credentials, enable messaging, activate cron/connectors, broaden permissions, or overwrite a live target.

## Core invariants

1. **One production authority at a time.** Never let two runtimes poll the same messaging credential.
2. **No secret bulk-copy.** Exclude `.env`, `auth.json`, OAuth/browser state, private keys, access tokens, cookies, and platform credentials. Transfer one separately approved credential or have the operator enter it locally on the target.
3. **Never replace a live target `state.db`.** Import history additively through supported APIs or collision-safe archival sessions.
4. **Target stays production-disabled during import.** Messaging, cron, connectors, webhooks, deployment authority, and external writes remain off until parity/recovery pass.
5. **Manifest before mutation.** Bind every copied file to relative path, size, SHA-256, class, mode, and target policy.
6. **Back up both sides.** Verify artifact, permissions, checksum/CRC, safe members, database integrity, and preferably a disposable restore.
7. **Preserve stronger target artifacts.** Do not downgrade reviewed/hardened Cloud files. Archive local variants and choose live authority explicitly.
8. **Receipts contain evidence, not secrets or transcripts.** Store counts, hashes, modes, booleans, and masked authority counts.
9. **Exact rollback only.** Restore/delete transaction-owned files, session IDs, config keys, and channel state.
10. **Counts are not parity.** Require hashes, SQLite integrity, behavior, persistence, permissions, and channel exclusivity.

## Select the migration mode

### Mode A — portable profile transfer

Use only when:

- the source is a safely exportable Hermes profile;
- target is new/disposable;
- all required data is inside the export scope;
- no live target history must be preserved;
- credentials will be configured separately;
- no external workspace/vault/source/database/host bridge is required.

Current supported commands:

```bash
hermes profile export <source-name> -o <owner-only-output>.tar.gz
hermes profile import <archive>.tar.gz --name <staging-name>
```

Named-profile exports exclude `.env` and `auth.json`. Inspect archive members anyway. A default-profile export has different root filtering and must be audited rather than assumed equivalent.

Mode A still requires archive hash, safe-member inspection, disposable import, persona/tool/memory/session verification, and separate production activation.

### Mode B — full-state migration

Use when any apply:

- custom or Dockerized `HERMES_HOME`;
- managed Cloud source or target;
- project data outside the profile root;
- external workspace/vault/repository/plugin/script/database;
- target already has live sessions or stronger reviewed artifacts;
- complete compacted/inactive history is required;
- runtime layouts/versions differ;
- cold rollback or reconstruction is required.

Mode B uses a sanitized manifest-bound file package, separate history transaction, and collision policy. Profile export may be one input but is not the whole migration.

### Mode C — production cutover

Mode C is never implied by A or B. It needs explicit approval after parity/recovery. It covers credentials, channel allowlists/toolsets, cron/connectors/callbacks, external writes, restart budget, messaging acceptance, exclusivity soak, and rollback triggers.

See `references/migration-mode-matrix.md` for the decision table.

## Standard evidence layout

Create an owner-only job root outside source and target:

```text
~/.hermes/state/profile-migrations/<migration-id>/
  00-contract.md
  01-source-inventory.json
  02-target-inventory.json
  03-source-backup-receipt.json
  04-target-backup-receipt.json
  05-candidate-manifest.json
  06-session-delta-plan.json
  07-apply-receipt.json
  08-parity-receipt.json
  09-cutover-receipt.json
  10-soak-receipt.json
  11-completion-receipt.md
```

Directories are `0700`; evidence/packages are `0600`. Encrypt secret-bearing rollback archives before they leave the protected host.

## Automation boundary

The bundled helpers automate deterministic **read-only preflight and verification**: scoped inventory, secret/runtime classification, SQLite evidence, session-delta planning, remapped-history idempotence, and file/hash/mode parity. They intentionally do not embed a generic authenticated Cloud mutation client. Managed Cloud APIs, provider layouts, and authorization can change; file apply, session import, backup retrieval, credential transfer, and cutover must use the current managed-Cloud operating workflow against the frozen contract and exact target. This keeps migrations fast without turning a reusable helper into unreviewed cross-agent write authority.

## Phase 0 — freeze the contract

Use `templates/migration-contract.md`. Record:

- migration ID/direction and source/target runtime types;
- profile names, absolute roots, runtime versions, and authority;
- owner/admin/collaborator boundaries;
- SOUL, memory, knowledge, skills, workspace, vault, source, plugins, scripts, cron, project databases, and session scope;
- target-owned artifacts to preserve;
- excluded secrets/runtime/dependencies/caches;
- production-disabled target requirements;
- behavior probes and reconstruction criteria;
- restart budget and automatic rollback triggers;
- approved credential/channel actions, normally none during data import;
- completion budget and stop conditions.

“All data” means legitimate substantive data—not credentials, auth state, caches, dependencies, temporary/recovery artifacts, or unrestricted production authority.

Before running bundled helpers, resolve an explicit Python 3.11+ interpreter. Use `python3.11` on macOS/Linux or `py -3.11` on Windows. Do not use an ambiguous `python3` alias unless `python3 --version` proves 3.11 or newer.

## Phase 1 — inventory source and target

Run the read-only helper:

```bash
python3.11 <skill-dir>/scripts/profile_inventory.py \
  --root <exact-profile-root-or-default-HERMES_HOME> \
  --profile-name <name> \
  --output <job>/01-source-inventory.json \
  --fail-on-secret-suspects
```

For a named profile, `--root` must be that exact profile directory (for example `~/.hermes/profiles/<name>`), never the containing `~/.hermes` or `profiles/` directory. For the default profile, use the default `HERMES_HOME`; the helper excludes its `profiles/` subtree so unrelated specialist profiles cannot enter the package. Run against an extracted target backup/mounted root or produce equivalent sanitized Cloud inventory. Do not expose authenticated browser state.

The inventory classifies substantive files, reviewed config, production authority, dynamic databases, credentials/secrets, runtime-local state, caches/dependencies/recovery artifacts, links, unsupported files, and secret-looking content without returning matched values. Secret scanning is chunked across the complete text/config file, including files larger than 2 MiB and quoted structured keys. SQLite is opened read-only for evidence; a non-empty WAL is counted but forces `snapshot_required` HOLD and makes the database non-transferable until an online-backup snapshot is supplied.

Inventory host bridges separately: aliases/wrappers, LaunchAgents/systemd, default-owned shims, shared scripts, external databases/repositories, mounts, and delivery/dedupe state.

## Phase 2 — freeze and back up

1. Resolve absolute roots; reject inherited `HOME`/`HERMES_HOME`/cwd drift.
2. Budget disk for source backup + candidate + disposable restore + operating floor.
3. Use SQLite online backup for a live database.
4. Seal source rollback outside the source tree.
5. Take a fresh target backup immediately before mutation.
6. Verify size, SHA-256, permissions, members, unsafe paths/links, CRC, restored hashes, and SQLite integrity.
7. Keep source authoritative until parity and recovery pass.

Cloud backup spawn/status alone is not independent proof; download and verify when required by the contract.

## Phase 3 — build the sanitized candidate

Require:

- one expected archive root and regular files only;
- no absolute paths, `..`, backslashes, links, devices, sockets, duplicates, or unsupported members;
- no `.env`, `auth.json`, keys/tokens, browser auth, logs, caches, dependency trees, Git internals, or recovery staging;
- production-disabled normalized config;
- cron/connectors/hooks/callbacks/external writes disabled unless separately approved;
- manifest path/size/hash/mode/class/source-authority/target-policy for every file;
- source authority via sealed Git bundle/ref/patch or reviewed working tree, not an unbounded `.git` copy;
- consistent snapshots and integrity checks for project databases;
- credential-path and high-confidence secret scan without printing matches.

Target policy is one of `install`, `preserve-target`, `archive-only`, or `exclude`. Never extract directly over the live target: quarantine, collision-audit, then apply transactionally.

## Phase 4 — reconcile session history

Run the transcript-free delta planner only on stable read-only source/target snapshots or disposable exports. It rejects non-empty WAL sidecars and a database that changes during reading:

```bash
python3.11 <skill-dir>/scripts/session_delta_plan.py \
  --source-db <source-state.db> \
  --target-db <target-state.db> \
  --output <job>/06-session-delta-plan.json
```

It compares stable session metadata, parent-session relationships, message-parent ordinals when present, and visible message sequences while omitting transcripts from the plan. It classifies:

- `no-op` — exact history is already represented under the same or a prior remapped archival ID, or the target is a verified superset;
- `import-new` — source session absent;
- `archive-copy` — target has a prefix/divergence/live traffic that must not be overwritten;
- `target-only` — retain target-native session;
- `blocked` — schema/integrity/relationship problems.

For `archive-copy`, use a deterministic collision-safe archival ID and import the complete normalized source session. This may intentionally duplicate overlapping context. Record unique missing rows separately from imported archive rows.

Before import, clear channel/thread/chat/origin/handoff/delivery routing and user identifiers per contract; strip hidden model reasoning; mark sessions ended/inactive/archived; preflight IDs/limits; and dry-run the same importer in a disposable DB. Require zero unexpected errors/skips/detached parents.

After import, page through imported sessions and hash-verify roles, visible content, timestamps, tool calls/results, and display metadata. Rollback deletes the exact imported session-ID set only.

## Phase 5 — apply files transactionally

1. Verify transport receipt/package hash.
2. Quarantine-extract with exclusive creation.
3. Audit collisions read-only.
4. Stage on the target filesystem.
5. Create a `0700` rollback directory and `0600` journal.
6. Apply only manifest paths with `overwrite=false` or atomic root swaps.
7. Preserve stronger target artifacts; archive uncertain local variants.
8. Read back and recompute every installed/archive SHA-256.
9. Verify databases, source authority, modes, and exact counts.
10. Retain rollback until post-import backup/disposable restore pass.

Passive file/history sync normally needs no restart. Do not spend a restart just to prove files exist.

Use `scripts/verify_manifest.py` for local/restored target hash and permission-mode verification. It binds to `hermes-profile-inventory/v1`, recomputes the inventory file-set identity, validates transferable-entry structure, rejects duplicate paths and unknown class selections, and requires the exact selected count. Mode parity is enforced by default; use `--ignore-mode` only when the frozen contract explicitly permits target-owned mode differences. Inventory errors, live-database snapshot requirements, unresolved secret suspects, and empty transfer sets fail. `--allow-excluded-secret-suspects` is permitted only after the contract records human adjudication of the listed paths; the files remain excluded and the override is recorded in the verification report.

## Phase 6 — parity and reconstruction

Require separate evidence lanes:

- **Identity:** persona/domain boundary and owner/admin/collaborator roles.
- **Knowledge:** memory, knowledge, vault, and forbidden-context non-visibility.
- **Capabilities:** skills/plugins/scripts/MCP/toolsets/model sentinel.
- **Projects:** workspace/source paths, bundle/ref, project DB integrity, CLI smoke.
- **History:** all source rows represented, target traffic retained, imports archived/routing-cleared.
- **Persistence:** restart or stop/start probe when approved.
- **Recovery:** post-import backup and production-disabled disposable restore.
- **Security:** exact-runtime audit passes or explicit candidate-bound exception remains visible.
- **Authority:** messaging/connectors/cron/external writes remain disabled before cutover.

Always issue two verdicts:

```text
Operational readiness: PASS | HOLD | FAIL
Data/content completeness: PASS | HOLD | FAIL
```

## Phase 7 — production cutover

After explicit approval only:

1. Revalidate contract/packet hash and backups.
2. Stage non-secret policy with target messaging disabled.
3. Stop source poller and prove it stopped.
4. Prove target is still disconnected and there is no dual polling.
5. The operator enters the credential on the target themselves by default. Existing-token transfer requires explicit one-shot approval and provider identity validation.
6. Read back messaging and gateway config; verify list types/counts/admin subset.
7. Start/restart target once within budget.
8. Require target health, connected channel count, provider identity, and source stopped state.
9. Run fresh inbound and exact harmless outbound probes.
10. Verify session/provider delivery evidence and observe conflicts/errors/disconnects/unauthorized access.

Automatic rollback order:

1. Disable/stop target messaging.
2. Prove target poller stopped.
3. Restore/start source authority.
4. Verify exactly one poller and bidirectional behavior.
5. Record evidence.

## Phase 8 — post-cutover delta and closeout

Freeze the stopped source and compare it against the current live target again:

- fresh target pre-sync backup;
- recompute files/history against current target, not the original candidate;
- additively import missing history;
- install only clearly authoritative missing live files;
- archive differing variants rather than downgrading target files;
- hash-verify readback;
- post-sync backup;
- remove plaintext staging;
- seal `templates/completion-receipt.md` with counts, hashes, exclusions, rollback, channel state, and open provider risks.

Only then call data completeness complete.

## Direction-specific rules

### Cloud → local/Docker

- download a full Cloud backup plus credential-stripped profile export when available;
- inspect `_external/` members before restore;
- restore into a sibling/disposable `HERMES_HOME`, never inside live `~/.hermes`;
- install a matching Hermes runtime separately because backups may omit code;
- keep local messaging off until Cloud polling is stopped;
- transfer credentials only after local behavior/recovery gates pass.

### Local/Docker → Cloud

- local stays authoritative through Mode B; Cloud stays production-disabled;
- after Mode C keep the stopped local runtime intact as cold rollback until soak passes.

### Cloud → Cloud

- source Cloud remains production authority;
- use a sanitized intermediate package, not shared credentials;
- compare target live history before import;
- keep target production-disabled through parity;
- stop source polling before enabling target;
- retain source stopped as cold rollback through soak.

## Fast checklist

- [ ] Contract/migration ID frozen; Mode A/B/C chosen.
- [ ] Source, target, bridges, versions inventoried.
- [ ] Source and target backups independently verified.
- [ ] Sanitized manifest-bound candidate built and scanned.
- [ ] Quarantine/collision audit passes.
- [ ] Files apply transactionally; hashes/modes verify.
- [ ] Session delta/dry-run passes; history imports additively.
- [ ] Imported content hashes and routing reset verify.
- [ ] Persona/knowledge/tools/projects/DB/source parity passes.
- [ ] Post-import backup and disposable restore pass.
- [ ] Exact-runtime security audit passes or exception is explicit.
- [ ] Separate cutover approval obtained.
- [ ] Source poller stops before target credential activation.
- [ ] Bidirectional messaging/exclusivity pass.
- [ ] Post-cutover delta and soak pass.
- [ ] Plaintext staging removed and receipts sealed.

## Common pitfalls

1. Treating profile export/import as a full Docker/Cloud/external-workspace migration.
2. Copying `.env` or auth because “all data” was requested.
3. Replacing live target `state.db` and erasing target traffic.
4. Appending compacted tails into existing sessions without collision analysis.
5. Comparing counts instead of paths/hashes/modes/DB integrity.
6. Downgrading a hardened target with an older local checkout.
7. Enabling target credentials before source poller stop proof.
8. Calling a backup spawn/exit code restore evidence.
9. Restoring under a path that resolves into live `~/.hermes`.
10. Copying `.git`, dependencies, caches, logs, locks, or recovery trees.
11. Treating a healthy dashboard status card as authenticated parity/reconstruction.
12. Trusting stale bot labels instead of provider-validated identity.
13. Calling cutover complete while a stopped-source delta remains.
14. Activating project-specific sensitive capabilities merely because files migrated. Approval workflows, financial or customer-record writes, third-party business-system connectors, callbacks, and staff-facing channels require separate release gates.
15. Hardcoding profile paths, usernames, IDs, hosts, or advisory sets into reusable tooling.

## Support files

- `scripts/profile_inventory.py` — read-only file/database classification.
- `scripts/session_delta_plan.py` — transcript-free history reconciliation.
- `scripts/verify_manifest.py` — target file/hash verification.
- `templates/migration-contract.md` — scope/authority/acceptance/rollback freeze.
- `templates/completion-receipt.md` — dual-verdict closeout.
- `templates/backup-receipt.md` — source/target backup verification.
- `templates/cutover-runbook.md` — single-poller credential cutover.
- `templates/rollback-receipt.md` — exact rollback evidence.
- `references/migration-mode-matrix.md` — fast mode/artifact decision table.

## Verification Checklist

- [ ] Frontmatter/support files validate.
- [ ] Helpers are read-only and never return secret values/message bodies.
- [ ] Credential/runtime/cache exclusions and symlink failures are tested.
- [ ] SQLite checks are read-only and bounded.
- [ ] Session planner distinguishes exact/new/prefix/divergent/target-only.
- [ ] Verifier detects missing/mismatch/type/unreadable files.
- [ ] Scripts use Python 3.11+ stdlib only.
- [ ] Synthetic fixture covers secrets, substantive files, authority, symlinks, SQLite, exact/prefix/divergent/target-only history.
- [ ] Optional read-only smoke against a real profile passes without source mutation (never commit its output).
- [ ] Creating/testing the skill changes no production profile, Cloud agent, credential, cron, connector, or gateway.

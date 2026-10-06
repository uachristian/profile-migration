# Hermes Profile Migration Contract

## Identification

- Migration ID:
- Requested by:
- Date/time (UTC):
- Direction: local→Cloud | Cloud→local | Docker→Cloud | Cloud→Docker | Cloud→Cloud
- Mode: A portable | B full-state | C cutover (separate authorization)

## Goal and non-goals

- Goal:
- Non-goals:
- Simplest acceptable outcome:
- Completion budget:
- Stop conditions:

## Source

- Runtime type/version:
- Profile name:
- Absolute `HERMES_HOME`:
- Workspace/vault/source/database roots:
- Current production authority:
- Current messaging pollers:
- Current crons/connectors/external writes:
- Source backup requirement:

## Target

- Runtime type/version:
- Profile name:
- Absolute target root:
- Existing target data/traffic:
- Target-owned artifacts to preserve:
- Production-disabled requirements:
- Target pre-change backup requirement:

## Data scope

Mark each `include`, `archive-only`, `preserve-target`, or `exclude`.

- SOUL/persona:
- profile description/config:
- memories:
- knowledge:
- skills:
- plugins/MCP:
- scripts:
- cron:
- workspace/projects:
- local vault:
- source authority/Git bundles:
- project databases:
- session history:
- compacted/inactive history:
- host bridges/wrappers/services:

## Mandatory exclusions

- `.env` and `auth.json`
- tokens, keys, cookies, OAuth/browser state
- caches, dependencies, logs, locks, PIDs, sockets
- Git internals unless a reviewed source-authority exception exists
- backups/recovery/staging artifacts
- unrestricted production authority
- unrelated personal/business/profile data

Additional exclusions:

## Authority and privacy

- Sole administrator:
- Non-admin collaborators:
- Allowed users/groups (counts or sealed attachment; no raw IDs in public receipt):
- Forbidden domains/data:
- Cross-profile boundaries:
- Project-specific sensitive gates:

## Acceptance criteria

- Source inventory:
- Candidate secret/path scan:
- File/hash/mode parity:
- SQLite integrity:
- Session representation/content hashes:
- Persona/knowledge/tool/project probes:
- Persistence/restart probe:
- Full backup/disposable restore:
- Security/dependency gate:
- Operational-readiness verdict:
- Data-completeness verdict:

## Cutover authorization (leave `NOT AUTHORIZED` until separately approved)

- Status: NOT AUTHORIZED
- Exact credential/channel:
- Source stop proof:
- Target start/restart budget:
- Inbound/outbound marker:
- Exclusivity observation window:
- Soak duration:

## Automatic rollback triggers

- duplicate polling
- failed inbound/outbound behavior
- unauthorized-user behavior
- health degradation
- unapproved security drift
- manifest/hash/integrity mismatch
- other:

## Exact rollback order

1. Disable/stop target messaging or mutation authority.
2. Prove target poller/writer stopped.
3. Reverse only transaction-journaled files/session IDs/config keys.
4. Restore/start source authority if cut over.
5. Verify exactly one authority and bidirectional health.
6. Seal rollback receipt.

## Approval

- Frozen contract SHA-256:
- Approved phases:
- Explicit exclusions/exceptions:
- Approval timestamp/source:

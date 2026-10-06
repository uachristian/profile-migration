# Hermes Profile Migration Completion Receipt

## Identity

- Migration ID:
- Direction/mode:
- Source runtime/profile:
- Target runtime/profile:
- Frozen contract SHA-256:
- Completion timestamp (UTC):

## Source evidence

- Source inventory SHA-256:
- Source backup path/class:
- Source backup size/SHA-256/mode:
- Archive/restore/SQLite verification:
- Source final authority state:

## Target evidence

- Target pre-change backup:
- Target post-import/post-sync backup:
- Independent download/hash/CRC/restore status:
- Runtime/version/security-audit identity:

## File migration

- Source scoped files/bytes:
- Already exact:
- Installed live:
- Archived variants:
- Preserved target-owned variants:
- Excluded by class:
- Readback hash/mode result:
- Project/source/database integrity:

## Session migration

- Source sessions/messages:
- Target pre-import sessions/messages:
- Exact/no-op sessions:
- New imported sessions/messages:
- Archival-copy sessions/messages:
- Unique source rows newly represented:
- Target-native sessions retained:
- Import errors/skips/detached parents:
- Routing/user-identity reset:
- Visible-content hash verification:
- Imported session-ID-set hash and rollback method:

## Authority/cutover

- Messaging credential copied: no | one-shot approved | owner entered locally
- Provider-side identity verified:
- Source poller stopped:
- Target poller connected:
- Allowed/admin/collaborator counts:
- Inbound/outbound test:
- Duplicate conflicts/errors/disconnects:
- Restart budget used/remaining:
- Cron/connectors/external-write state:

## Verdicts

- Operational readiness: PASS | HOLD | FAIL
- Data/content completeness: PASS | HOLD | FAIL
- Reconstruction/rollback readiness: PASS | HOLD | FAIL
- Security gate: PASS | EXCEPTION | HOLD | FAIL

## Intentional exclusions

- credentials/auth state:
- runtime/cache/dependency/log/recovery state:
- unrelated profile/business/personal data:
- project-specific capabilities not activated:

## Remaining work

- Soak end/status:
- Provider/runtime remediation:
- Deferred project-specific release gates:
- Backup-assurance gaps:

## Exact rollback

- Target files/roots owned by transaction:
- Imported session IDs or ID-set hash:
- Config keys changed:
- Credential/channel disable sequence:
- Source restoration/start sequence:
- Verification after rollback:

## Receipt sealing

- Receipt path:
- Mode:
- SHA-256:
- Plaintext staging removed:
- Canonical vault/project record updated:

# Hermes Profile Cutover Runbook (Mode C)

Mode C is never implied by a file or history import. Execute only after a separate, explicit approval.

## Single-poller rule

A messaging bot token (or any polling credential) must never be active in two runtimes at once.
Two pollers on one token cause dropped updates, conflict errors, and duplicate replies. The source
poller is stopped and proven stopped **before** the target receives or enables the credential.

## Preconditions

- [ ] Approval recorded (who, when, exact channel/credential, restart budget):
- [ ] Contract and cutover packet SHA-256 re-validated:
- [ ] Fresh source and target backups verified (`backup-receipt.md`):
- [ ] Target data parity and disposable restore passed:
- [ ] Target messaging, cron, connectors, and external writes still disabled:

## Steps

1. Stage non-secret channel policy on the target with messaging disabled; read it back.
2. Stop the source gateway/poller. Proof (process absent, platform disconnected):
3. Prove the target is still disconnected (no dual polling):
4. Credential: the operator enters it on the target themselves (default). A transfer of an existing
   token requires explicit one-shot approval. Never paste the value into chat, logs, or receipts.
5. Validate provider-side identity (bot username/ID as reported by the provider):
6. Read back messaging and gateway config; verify allowlist/admin counts (counts only):
7. Start or restart the target once within budget. PID/start time:
8. Health: connected channel count, provider identity, source still stopped:
9. Fresh inbound probe and one harmless outbound probe:
10. Observe for the agreed window: conflicts, errors, disconnects, unauthorized access.

## Automatic rollback triggers

- duplicate polling or conflict errors
- failed inbound/outbound probe
- unauthorized-user behavior
- health degradation or restart budget exhausted

## Rollback order

1. Disable/stop target messaging.
2. Prove the target poller stopped.
3. Restore/start source authority.
4. Verify exactly one poller and bidirectional behavior.
5. Fill `rollback-receipt.md`.

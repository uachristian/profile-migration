# Hermes Profile Migration Backup Receipt

Record evidence only. Never paste secrets, tokens, transcripts, or raw user identifiers.

## Identity

- Migration ID:
- Side: source | target
- Runtime type: local | Docker | managed Cloud
- Profile name:
- Profile root (relative to the job root or a placeholder, not a machine path):
- Taken at (UTC):

## Artifact

- Method: SQLite online backup + file archive | Cloud backup download | profile export
- Artifact class: rollback (secret-bearing, encrypted) | sanitized
- Size (bytes):
- SHA-256:
- File mode (expect 0600):
- Encrypted at rest: yes | no (explain)

## Verification

- Archive members listed and safe (no absolute paths, `..`, links, devices): PASS | FAIL
- Archive CRC / integrity: PASS | FAIL
- Disposable restore into a sibling root (never inside the live Hermes home): PASS | FAIL | SKIPPED (reason)
- Restored file-hash parity vs inventory: PASS | FAIL
- SQLite `PRAGMA integrity_check` on restored databases: ok | errors
- Non-empty WAL at capture time: no | yes (snapshot re-taken)

## Verdict

- Backup usable for rollback: PASS | HOLD | FAIL
- Notes:

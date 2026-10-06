# Hermes Profile Migration Rollback Receipt

## Identity

- Migration ID:
- Trigger (which automatic or manual condition fired):
- Started / finished (UTC):

## Authority

- Target poller/writer stopped (proof):
- Source authority restored/started (proof):
- Exactly one active poller confirmed: yes | no
- Bidirectional probe after rollback: PASS | FAIL

## Reversed changes (transaction-journaled only)

- Target files removed/restored (count, journal SHA-256):
- Imported session IDs deleted (count, ID-set SHA-256):
- Config keys reverted:
- Credential disabled on target: yes | n/a

## Verification

- Target file/hash parity vs pre-change backup: PASS | FAIL
- SQLite integrity on target databases: ok | errors
- Nothing outside the transaction journal touched: yes | no (explain)

## Verdict

- Rollback complete: PASS | HOLD | FAIL
- Follow-up:

# Migration Mode Matrix

## Fast selection

| Condition | Mode | Primary transport | Required additions |
|---|---|---|---|
| New local target; all data inside named profile; no live target state | A | `hermes profile export/import` | hash, member audit, disposable import, credentials separate |
| Default profile export | A with audit | supported export | inspect root allowlist and credential exclusions; never assume named-profile behavior |
| Docker/custom `HERMES_HOME` | B | sanitized manifest package | mounted-root inventory, external projects, runtime exclusions, DB snapshots |
| Managed Cloud is source or target | B | Cloud backup/export + authenticated file/session APIs | target backup, quarantine, additive sessions, reconstruction proof |
| Target already has sessions/production traffic | B | additive file/history transactions | no `state.db` replacement; archive divergent source sessions |
| Cloud → Cloud | B then optional C | sanitized intermediate package | source stays authoritative; target disabled; one-poller cutover |
| Production messaging moves | C | separate credential/channel transaction | source stop, target start, provider identity, bidirectional test, soak |
| Only source code/procedures move; user data stays | Distribution | `profile install/update` | distribution manifest/version; user memory/auth preserved |

## Artifact expectations

### Mode A

- frozen contract
- source inventory
- credential-stripped `.tar.gz`
- archive SHA-256/member-safety receipt
- disposable import verification
- target profile verification
- separate credential setup/cutover receipt if activated

### Mode B

Everything in Mode A when applicable, plus:

- full source rollback
- fresh target pre-change backup
- external-root inventory
- manifest-bound sanitized package
- quarantine/collision receipt
- transaction journal/rollback directory
- source/target session delta plan
- normalized history payload and dry-run receipt
- file/session readback hashes
- project DB/source-authority verification
- post-import backup and disposable restore
- post-cutover stopped-source delta sync

### Mode C

- exact cutover authorization/packet hash
- source and target fresh backup evidence
- tokenless target policy readback
- source-poller stop proof
- one credential entry/transfer receipt without value/fingerprint
- target config-layer parity and restart PID/budget
- provider identity and platform connected counts
- inbound/outbound session/provider evidence
- duplicate/error/disconnect/unauthorized counters
- cold rollback state and soak receipt

## Direction notes

### Local/Docker → Cloud

Keep local authoritative through Mode B. Cloud remains disabled. After Mode C, keep the stopped local runtime intact as cold rollback until soak and provider/security gates finish.

### Cloud → local/Docker

Download and independently audit a full Cloud backup. Restore into a sibling disposable root with matching runtime. Keep local channels disabled until Cloud polling stops. Cloud remains cold rollback after transfer.

### Cloud → Cloud

Never copy source Cloud credentials into a broad package. Move data through a sanitized intermediate artifact, verify target while disabled, then transfer one channel credential only after the source poller stops.

### Profile distribution instead of migration

Use a distribution when the goal is versioned persona/config/skills/cron source shared across installations while local memories, sessions, credentials, and user edits remain target-owned. A distribution is not a state migration or disaster-recovery archive.

## Mandatory stop conditions

- source/target identity or root uncertain
- source backup missing/unverified
- target pre-change backup missing when mutation is planned
- secret/path scan finding
- archive unsafe member/link/device/duplicate
- SQLite integrity error or unexplained parent/message collision
- target artifact authority ambiguous
- target production authority unexpectedly enabled
- two pollers/writers could become active
- restart budget exhausted
- provider/runtime incompatibility for required callbacks/tools
- unapproved dependency/security drift
- insufficient disk for backup + candidate + restore + operating floor

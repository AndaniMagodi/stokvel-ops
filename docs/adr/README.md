# Architecture Decision Records

One file per decision that was genuinely contested. If there was only ever
one sensible option, it does not need an ADR.

An ADR is worth writing when you can name a real alternative and say why you
rejected it. The rejected options are the valuable part — they are the
evidence that a decision was made rather than defaulted into. Write them while
the trade-off is still fresh; reconstructing your reasoning three weeks later
produces a rationalisation, not a record.

ADRs are immutable once accepted. If a decision changes, write a new ADR that
supersedes the old one and mark the old one `Superseded by NNNN`. Never edit
history.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-record-keeping-not-custodial.md) | Record-keeping rather than custody of funds | To write |
| [0002](0002-message-broker.md) | Which message broker | To write |
| [0003](0003-data-ownership.md) | Schema-per-service in one instance | To write |
| [0004](0004-database-enforced-ledger-invariants.md) | Ledger invariants live in the database | Accepted |

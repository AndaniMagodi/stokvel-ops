# 0004. Enforce ledger invariants in the database, not the service layer

- **Status:** Accepted
- **Date:** 2026-09-05

## Context

The ledger is the one part of this system where a bug is not recoverable by
retrying. If a contribution is double-posted or a transaction commits
unbalanced, the group's records are wrong and no amount of later correctness
repairs the trust the product exists to provide.

Three things will legitimately write to these tables over the system's life:
the ledger service, database migrations, and a human with `psql` during an
incident. Any invariant enforced only in application code is unenforced for
two of those three.

## Options considered

### Option A — enforce in the service layer

Validate legs balance, reject zero amounts, check idempotency by querying
before inserting. Simple, portable across databases, easy to unit test with
no infrastructure.

Costs: the "check then insert" idempotency pattern is a race — two concurrent
webhook redeliveries can both pass the check. Nothing protects the tables from
a second writer or a manual fix. The invariant lives in whichever code path
happens to be correct today.

### Option B — enforce in the database

Unique indexes for identity and idempotency, `CHECK` constraints for
single-row rules, and deferred constraint triggers for the multi-row rule
(legs sum to zero, checked at `COMMIT` when the whole set is visible).
Append-only enforced by a trigger that rejects `UPDATE` and `DELETE`.

Costs: the rules are written in PL/pgSQL, which is a second language in the
repo and less familiar to most readers. It binds the project to Postgres. The
test suite must run against real Postgres, which makes tests slower and
requires infrastructure to be up. Errors surface as `DBAPIError` and have to
be translated into domain exceptions.

### Option C — event sourcing with a projected balance

Store only events; derive everything. Gives a perfect audit trail and makes
"balance at time T" trivial.

Costs: projection lag, rebuild tooling, and versioned event schemas — a large
amount of machinery for a domain whose write volume is a handful of
transactions per group per month.

## Decision

Option B. Identity and idempotency are unique indexes; the balance,
minimum-leg-count and single-currency rules are one deferred constraint
trigger; append-only is a `BEFORE UPDATE OR DELETE` trigger.

The service layer still validates, but as *fast, friendly failure* — the
database remains the thing that makes the invariant true.

## Rationale

Postgres-only was already true (Option C would not have changed that), so
database-specific enforcement costs nothing that was not already spent. The
deciding factor was the idempotency race: it cannot be closed in application
code without a unique index, and closing it is the whole reason the ledger can
sit behind an at-least-once webhook.

Accepting slower tests was a deliberate trade. Substituting SQLite for speed
would test a system that does not have these guarantees, which is worse than
having no test.

## Consequences

- The test suite requires a running Postgres. Isolation is by `TRUNCATE`
  rather than transaction rollback, because deferred constraint triggers fire
  at `COMMIT` — a test wrapped in a rolled-back transaction would never see
  them fire and would pass on broken data.
- `TRUNCATE` is safe here specifically because it does not fire row-level
  `DELETE` triggers. Switching to per-row cleanup would hit the append-only
  trigger.
- The service must be written to *catch* constraint violations and translate
  them, not to avoid reaching them. A pre-check is an optimisation.
- Corrections are made by posting a reversing transaction, never by editing.
  Every user-facing "undo" needs a compensating entry, which is also what
  makes the payout saga (step 6) tractable.
- Revisit if this ever needs to run on a database without deferred constraint
  triggers, or if write volume grows enough that per-commit trigger cost
  matters. Neither is plausible at stokvel scale.

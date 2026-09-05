# stokvel-ops

A WhatsApp-first stokvel (rotating savings group) coordination platform, built as
an event-driven system across four services.

This is a learning-first build. The point is not the feature list — it is being
able to explain, and defend, every architectural decision in it. The
`docs/adr/` directory is therefore as much a deliverable as the code.

## Scope boundary

This system **records and coordinates**; it never holds member funds. Members
pay each other or a group account directly, and the platform verifies,
reminds, reconciles, and keeps an auditable history. Custody of member money
would put this under FSCA/FAIS and national payment-system regulation, which
is a legal project rather than a software one — and it would not add a single
architectural pattern that isn't already here.

## Target architecture

Four services, split by reason-to-change and failure profile rather than by
noun:

| Service | Owns | Why it is separate |
|---|---|---|
| `ledger` | Groups, members, cycles, contributions, payouts, the double-entry ledger, the outbox | Highest correctness bar, changes least, strictest tests |
| `wa-gateway` | The only code that knows WhatsApp exists — signature verification, dedupe, rate limits, the 24h window | Bursty traffic, external-API failure profile, swappable for SMS |
| `conversation` | The chat state machine; translates messages into domain commands and events into replies | Changes constantly (copy, flows); must be structurally unable to corrupt money |
| `scheduler` | Cycle timers, reminder fan-out, grace-period expiry, dunning | Time-triggered — a genuinely different execution model |

Four is the ceiling. A fifth candidate is usually a package, not a service.

**Only `ledger` exists today.** The other three are steps 3–6 of the build
order, and scaffolding them now would let you skip the thinking they exist to
teach.

## Build order

| # | Step | Status |
|---|---|---|
| 0 | Ledger invariants written as tests, before the code | scaffolded |
| 1 | `ledger`: double-entry postings, balances, idempotency, reversal | **you are here** |
| 2 | Cycle lifecycle: open, contribute, shortfall, close | not started |
| 3 | `wa-gateway` with a fake adapter and a message simulator | not started |
| 4 | Wire gateway → `conversation` → ledger over the broker; introduce the outbox | not started |
| 5 | `scheduler` + rate-limited reminder fan-out | not started |
| 6 | Payout saga with compensation | not started |
| 7 | Real Meta adapter, then a payment-provider webhook | not started |
| 8 | React treasurer dashboard | not started |
| 9 | Tracing, chaos tests, load test, ADRs written properly | not started |

## Running it

```bash
make up                 # postgres (dev on 5434, test on 5435)
cd services/ledger && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
make migrate            # apply the ledger substrate migration
make test               # 11 pass, 20 fail — see below
```

`make test` is expected to be partly red right now. That is the starting
state, not a broken checkout:

- **11 passing** — `tests/test_database_invariants.py`, which tests guarantees
  the *database* enforces. These are the floor, and they hold no matter what
  the application layer does.
- **20 failing** — `tests/test_ledger_service.py`, the specification for the
  four functions you are about to write. Every failure is a
  `NotImplementedError`.

Run `HYPOTHESIS_PROFILE=thorough make test` before you call step 1 finished:
that raises property-based examples from 25 to 200 per test.

## The ledger model

Three tables form the substrate. Everything else in the domain will be built
on top of them.

- **`accounts`** — one per (group, kind, member). `kind` is the role the
  account plays: `member_contributions`, `group_pot`, `payout_clearing`,
  `external`. A group-level account such as the pot has a `NULL` member.
- **`ledger_transactions`** — one per business event, carrying the
  `idempotency_key` that makes replay safe.
- **`ledger_entries`** — the signed legs. Positive is a debit, negative a
  credit, and every transaction's legs sum to zero.

Money is `bigint` cents. Never a float, never a `Numeric` you might be tempted
to round.

### What the database enforces, and why

The design principle is that **correctness invariants belong in the database**,
because that is the one layer no buggy service, retry, or manual `psql`
session can route around.

| Invariant | Mechanism |
|---|---|
| Every transaction's legs sum to zero | Deferred constraint trigger, checked at `COMMIT` |
| Every transaction has at least two legs | Same trigger — a one-leg transaction cannot balance |
| A transaction never mixes currencies | Same trigger |
| No zero-amount leg | `CHECK (amount_cents <> 0)` |
| Entries and transactions are append-only | `BEFORE UPDATE OR DELETE` trigger that raises |
| One transaction per (group, idempotency key) | Unique index — **this is the real idempotency guarantee** |
| One account per (group, kind, member), NULL member included | Unique index with `NULLS NOT DISTINCT` |
| A transaction can be reversed at most once | Partial unique index on `reverses_transaction_id` |

Two of these are worth understanding properly rather than just using:

**Why the balance check is a *deferred* constraint trigger.** A `CHECK`
constraint sees one row; balancing is a property of a set of rows. A normal
`AFTER INSERT` trigger would fire after the first leg, when the transaction is
legitimately unbalanced. `DEFERRABLE INITIALLY DEFERRED` moves the check to
`COMMIT`, when the full set is visible. This is also why the test suite
isolates by `TRUNCATE` instead of by rolling back a wrapping transaction — a
test that never really commits would never see these triggers fire, and would
pass while the invariant was broken.

**Why the unique index is the idempotency guarantee.** Application-level
"check whether this key exists, then insert" is a race: two concurrent
webhook redeliveries both check, both find nothing, both insert. The unique
index is what actually makes double-posting impossible. Everything above it —
caches, early returns — is optimisation, not correctness. Your service should
be written to *catch the constraint violation*, not to prevent reaching it.

### Where the database stops

Deliberately left to the service layer, so that the work is real:

- **Entry currency must match its account's currency.** The database checks
  that a transaction is internally consistent, not that each leg matches the
  account it hits. Raise `CurrencyMismatch`.
- **Every leg's account must belong to the transaction's group.** Nothing
  stops a cross-group posting at the schema level. Raise `AccountNotInGroup`.
- **Empty leg lists.** A transaction with zero entries never fires the
  row-level trigger, so it would commit. Raise `EmptyTransaction`.
- **Turning a constraint violation into a clean idempotent result.** The
  database will tell you "duplicate key". Deciding whether that means *return
  the existing transaction* (same request replayed) or *reject* (same key,
  different payload — `IdempotencyKeyConflict`) is the interesting part.

That last distinction is the one most implementations get wrong, and it is
worth an ADR of its own.

## Your next step

Implement four functions and make the red tests green:

- `app/ledger/accounts.py` → `ensure_account`
- `app/ledger/service.py` → `post_transaction`, `account_balance`,
  `group_balances`, `reverse_transaction`

The contract they must satisfy is `app/ledger/posting.py` (the request and
result shapes) and `app/ledger/errors.py` (the failures the tests expect).
Neither needs changing — if you find yourself wanting to change one, that is a
design argument worth writing down in an ADR first.

There is no HTTP router yet, on purpose. Get the domain right, then decide
what to expose.

### One trap in the test harness

The `db` fixture is function-scoped, but Hypothesis runs many examples inside
a single test function. State therefore **accumulates across examples within
one test**. The property tests here are written to be safe under accumulation
(they either assert a global invariant, or create fresh accounts per example).
If you add a property test that assumes an empty database, it will pass
locally and fail as soon as `max_examples` changes. Assert invariants, not
absolute values.

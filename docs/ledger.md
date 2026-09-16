# Ledger design and next step

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

# stokvel-ops

A treasurer tool for recording stokvel contributions, fines, and payment proofs.
The first goal is to process one real monthly cycle with a clear explanation
for every amount recorded. The system records payments; it does not hold funds.

## What exists

- A Python/FastAPI backend in `services/ledger`.
- A PostgreSQL ledger schema with database-enforced balance and history rules.
- A pure calculation for contribution windows and payment allocations.

Manual payment review and confirmation are available through the local API.
PDF, PNG, and JPEG proofs can be uploaded for suggested fields. A member
directory can suggest who paid when the payment reference matches a registered
alias. A treasurer interface is not built yet.

## Next workflow

The treasurer reviews a payment proof, matches it to a member, confirms the
payment, and previews how the amount settles carried fines and the current
contribution. August's contribution window, for example, is 8 August through
7 September. See [the contribution rules](docs/contribution-workflow.md).

After running migrations, open `http://localhost:8001/docs`:

1. `POST /members` registers a name and one or more payment references. You
   can supply an existing `member_id` to keep earlier payment records linked.
   `GET /groups/{group_id}/members` lists the directory.
2. `POST /payments/proof/inspect` accepts one PDF, PNG, or JPEG (up to 5 MB;
   PDFs up to 3 pages) and suggests a date, amount, and reference. Supply
   `group_id` in the form to suggest a member when its reference matches a
   registered alias. OCR can change spacing, which matching ignores. It saves
   nothing. Check the proof and bank statement yourself. Payment links are
   entered manually for now.
3. `POST /missed-months` records a missed month after its 7th-of-next-month
   cutoff. For now this is a manual step based on the treasurer's records.
4. `POST /payments/preview` reads that member's outstanding months and shows
   the fines, contribution, and red-to-green changes. It saves nothing.
5. `POST /payments/confirm` recalculates and saves the reviewed payment,
   month settlements, and balanced ledger posting together. Reusing the same
   `proof_key` returns the original confirmation without posting money again.

Use stable group and member UUIDs, a unique `proof_key` for each POP (for
example, the bank notification's document ID), the payment date, its reference,
and the amount in **cents**. Confirm receipt in the group bank account before
using the confirm endpoint. The API is bound to localhost and has no user
authentication yet; use test data while reviewing the workflow.

## Run the backend

From the repository root:

```bash
make up
cd services/ledger
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
cd ../..
make migrate
make test
```

The test suite covers the ledger, contribution rules, payment workflow, and
proof field suggestions.

## Repository map

| Path | Purpose |
|---|---|
| `services/ledger/app/ledger/` | Ledger posting and balance service |
| `services/ledger/app/contributions/` | Payment rules, workflow, and proof extraction |
| `services/ledger/app/models/` | Database models |
| `services/ledger/alembic/` | Database migration |
| `services/ledger/tests/` | Ledger specifications |
| `docs/contribution-workflow.md` | Treasurer workflow and confirmed rules |
| `docs/ledger.md` | Ledger design and implementation notes |
| `docs/adr/` | Accepted architecture decisions |
| `docs/future-ideas.md` | Ideas after the first real monthly cycle |

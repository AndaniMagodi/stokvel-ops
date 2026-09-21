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

1. `POST /members` registers a name, payment references, and optionally the
   contact number and first month they were expected to contribute. You can supply an existing
   `member_id` to keep earlier records linked. Existing members can use
   the contact-number and first-expected-month `PATCH` endpoints.
   `GET /groups/{group_id}/members` lists the directory.
   `POST /groups/{group_id}/members/import` reads the `MEMBERS` and
   `CONTACT NO` columns from an XLSX workbook and reports missing or shared
   numbers without guessing them.
2. `POST /payments/proof/inspect` accepts one PDF, PNG, or JPEG (up to 5 MB;
   PDFs up to 3 pages) and suggests a date, amount, and reference. Supply
   `group_id` and `sender_phone` in the form to suggest a member. Matching uses
   the phone number and the POP reference, including initial-plus-surname forms.
   A unique phone can match by itself; shared numbers require the reference.
   Conflicts are returned for manual review. Set `use_ai=true` to use Groq's structured extraction
   when bank wording differs; this sends extracted proof text to Groq and
   requires `GROQ_API_KEY` in `services/ledger/.env`. The default local
   extraction stays on your machine. OCR can change spacing, which matching
   ignores. Inspection saves nothing. Check the proof and bank statement
   yourself. Payment links are entered manually for now.
3. `GET /groups/{group_id}/missed-months/review` lists registered members with
   no recorded payment in each closed contribution month, from their first
   expected month onward. It also lists members whose first month is unset.
   After checking against the bank statement, use
   `POST /groups/{group_id}/missed-months/confirm` to record R100 per missed
   month. Repeating it does not add another fine. `POST /missed-months` remains
   available for one manually reviewed month.
4. `POST /payments/preview` reads that member's outstanding months and shows
   the fines, contribution, and red-to-green changes. It saves nothing.
5. `POST /payments/confirm` recalculates and saves the reviewed payment,
   month settlements, and balanced ledger posting together. Reusing the same
   `proof_key` returns the original confirmation without posting money again.
6. `GET /groups/{group_id}/months/{year}/{month}` returns the spreadsheet-style
   monthly view and totals. Statuses are `normal` for an ordinary payment,
   `red` for a missed month with an unpaid fine, `green` only when a formerly
   red month is fully cleared, `pending_review` for a closed unrecorded month,
   and `pending` while the contribution window is still open.

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

# stokvel-ops

A treasurer tool for recording stokvel contributions, fines, and payment proofs.
The first goal is to process one real monthly cycle with a clear explanation
for every amount recorded. The system records payments; it does not hold funds.

## What exists

- A Python/FastAPI backend in `services/ledger`.
- A PostgreSQL ledger schema with database-enforced balance and history rules.
- Tests that specify the unfinished ledger posting service.

POP intake, contribution allocation, and a treasurer interface are not built yet.

## Next workflow

The treasurer reviews a payment proof, matches it to a member, confirms the
payment, and previews how the amount settles carried fines and the current
contribution. August's contribution window, for example, is 8 August through
7 September. See [the contribution rules](docs/contribution-workflow.md).

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

The current test suite is intentionally partly red: the ledger service
functions have not been implemented. See [the ledger design](docs/ledger.md)
for its invariants, test status, and next coding step.

## Repository map

| Path | Purpose |
|---|---|
| `services/ledger/app/ledger/` | Ledger posting contracts and unfinished service |
| `services/ledger/app/models/` | Database models |
| `services/ledger/alembic/` | Database migration |
| `services/ledger/tests/` | Ledger specifications |
| `docs/contribution-workflow.md` | Treasurer workflow and confirmed rules |
| `docs/ledger.md` | Ledger design and implementation notes |
| `docs/adr/` | Accepted architecture decisions |
| `docs/future-ideas.md` | Ideas after the first real monthly cycle |

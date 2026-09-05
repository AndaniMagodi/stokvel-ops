LEDGER := services/ledger

.PHONY: up down logs migrate revision test test-watch shell fmt

up:
	docker compose up -d db db-test
	docker compose ps

down:
	docker compose down

logs:
	docker compose logs -f ledger

migrate:
	cd $(LEDGER) && alembic upgrade head

revision:
	cd $(LEDGER) && alembic revision -m "$(m)"

test:
	cd $(LEDGER) && pytest -q

test-watch:
	cd $(LEDGER) && pytest -q --hypothesis-show-statistics

shell:
	docker compose exec db psql -U postgres -d stokvel

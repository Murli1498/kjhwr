PY := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

.PHONY: test api ui docker fetch

test:
	$(PY) -m pytest

api:
	$(PY) -m uvicorn backend.main:app --reload --port 8000

ui:
	cd frontend && npm run dev

fetch:
	$(PY) scripts/fetch_elexon.py

docker:
	docker compose up --build

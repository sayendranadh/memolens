.RECIPEPREFIX = >
.PHONY: install verify-env probe seed-data demo-seed eval eval-quick \
        run-backend test clean frontend-install frontend-dev frontend-build

install:
> pip install -r requirements.txt

verify-env:
> python backend/verify_env.py

probe:
> python tools/probe_hindsight.py

seed-data:
> python -m backend.generate_data

demo-seed:
> python -m backend.seed

eval:
> python -m eval.eval

eval-quick:
> python -m eval.eval --batches 1,2

run-backend:
> uvicorn backend.main:app --reload --port 8000

test:
> pytest

frontend-install:
> cd frontend && npm install

frontend-dev:
> cd frontend && npm run dev

frontend-build:
> cd frontend && npm run build

clean:
> rm -rf data/llm_cache/ eval/results/ .pytest_cache/
> find . -name __pycache__ -type d -prune -exec rm -rf {} +

TRAVAIL ?= travail
PATIENTS ?= 500
GRAINE ?= 0

.PHONY: all generate phenotype evaluate test lint typecheck check clean

all: generate phenotype evaluate

generate:
	uv run sjs-phenotype generer --sortie $(TRAVAIL) --patients $(PATIENTS) --graine $(GRAINE)

phenotype:
	uv run sjs-phenotype phenotyper --travail $(TRAVAIL)

evaluate:
	uv run sjs-phenotype evaluer --travail $(TRAVAIL)

test:
	uv run pytest

lint:
	uv run ruff check src tests

typecheck:
	uv run mypy

check: lint typecheck test

clean:
	rm -rf $(TRAVAIL)

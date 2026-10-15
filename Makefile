# Developer entry points.
# Every command is reproducible from a clean clone of the repository.
#
# Note: recipe lines MUST be indented with a tab character.

.PHONY: install ingest build test docs clean all

export DBT_PROFILES_DIR := $(PWD)/transform

RAW_FILE ?= data/raw/OPEN_PHMEV_2025.CSV
YEAR     ?= 2025

install:
	pip install -r requirements.txt
	cd transform && dbt deps

ingest:
	python -m ingestion.sources.phmev --path $(RAW_FILE) --year $(YEAR)

build:
	cd transform && dbt build

test:
	cd transform && dbt test

docs:
	cd transform && dbt docs generate && dbt docs serve

clean:
	rm -rf warehouse/*.duckdb transform/target transform/logs

all: ingest build

tables:
	python -m scripts.query --list

check:
	python -m scripts.check_repo
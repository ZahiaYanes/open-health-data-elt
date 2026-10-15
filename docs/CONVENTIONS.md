# Repository Conventions

## Language
All code, comments, docstrings, commit messages and documentation are in **English**.
(Data source names and French administrative codes keep their original naming.)

## Python
- Every module starts with a module-level docstring: purpose, inputs, outputs.
- Every public function has a docstring (one-line summary + Args/Returns).
- Inline comments explain **why**, not **what**.
- Type hints everywhere.

## SQL / dbt
- Every model starts with a SQL comment block: grain, source, business meaning.
- CTE-based structure: `source` -> `renamed` / `filtered` -> `final`.
- Every model and column is documented in the matching `_*.yml` file.

## Notebooks
Notebooks are for **exploration and demonstration only** - never for production logic.
Rules:
1. Each notebook lives in `notebooks/` and is numbered: `01_*.ipynb`.
2. Each notebook has a **companion markdown file** `notebooks/01_*.md`
   explaining: objective, inputs, outputs, key findings, how to re-run.
3. `notebooks/README.md` lists all notebooks with a one-line summary.
4. Markdown cells must frame every code cell: what we do and why.
5. Any logic that proves useful is **promoted** to `ingestion/` or `transform/`.

## Decisions
Every non-obvious technical choice is recorded as an ADR in `docs/adr/`.
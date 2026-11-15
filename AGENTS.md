# eaip-lib
Python library that fetches and parses data from the NATS UK eAIP (async: aiohttp/aiofiles, BeautifulSoup).
It is the data source for the sibling project ../caa-map, which draws a 1:500,000 VFR chart.

## Rules
- Python 3.14 via uv. Run with `uv run <cmd>`; add deps with `uv add`. Never use system python or pip.
- Find how tests run (Makefile, tests/) before assuming a runner. Run only the tests relevant to the task.
- The code makes live HTTP requests to NATS. Never run code that fetches from the network unless told to.
  Prefer saved fixture files in tests/. Never loop, retry in a loop or fetch in bulk. Be polite: one request at a time.
- Downloaded eAIP pages/data are large. Don't open them in full; use `head -c 500` or `grep -n`.
- Ignore docs/_build, .venv and data files (see .ignore).
- One task per session. Before editing, list the files you will change (max 3).
- No refactors, renames or new features beyond the task. No new dependencies without asking.
- Don't weaken or delete tests to make something pass. Keep public function signatures unless the task says otherwise.
- Output data must stay plain, documented structures (dict/dataclass/JSON) because caa-map consumes them.
  Coordinates are WGS84 decimal degrees unless the task says otherwise. State units for any numeric field.
- If something fails twice, stop and report instead of trying more approaches.
- End each session by appending 3-5 lines to docs/PROGRESS.md: done / next / issues.

## Commands
- Tests: `uv run python -m unittest discover -s tests` (test files must be named test_*.py)
- Docs: `make -C docs html` (only when told)

## Working from PLAN.md
- You are given a task ID (for example E2). Read only that task: `grep -n -A30 "^### E2" PLAN.md`.
- Do only that task. Respect its Files and Do-not lists and its acceptance check.
- If it needs more than stated, stop and report instead of widening scope.
- When done: tick its checkbox in PLAN.md and append to docs/PROGRESS.md. Edit nothing else outside the task.

## Orientation
- docs/OVERVIEW.md summarises the repo (files, API, data extracted, fetching). Read it first when the task says "Read: OVERVIEW"
  or you need to find where something lives. Prefer it over exploring the code. If it disagrees with the code, trust the code and say so.

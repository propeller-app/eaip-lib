# eaip-lib plan
Goal: extract everything caa-map needs from the NATS eAIP and export it as JSON in caa-map's schema
(see ../PLAN.md data contract). Tasks are small and independent. One per session.
Fixtures are saved eAIP pages in tests/fixtures/. The human saves them; never fetch from the network.

## Known issues
- Line.end uses the regex-type ordinal as a segment index (wrong after the first segment)
- get_airfields_icao misses an await when eaip_date is None
- Latest-release discovery fires ~30 concurrent requests
- tests/airfield.py hits the live site and is not found by unittest discovery
- Pickle cache at ~/.cache/eaip-lib can break across code changes; no expiry
- ppr is hardcoded False

## Tasks

### E1 [x] Offline airfield test
Human prerequisite: tests/fixtures/EG-AD-2.EGKR.html saved from the live eAIP (large: read with grep -n / head -c only).
Files: tests/ only. Rewrite tests/airfield.py to use eaip.get_airfield_from_raw_html on the fixture with a fixed
datetime; rename to tests/test_airfield.py. Assert icao EGKR, the name, lat/long within 0.01, at least one runway
and one radio. Report the expected values and where in the fixture you read them.
Check: `uv run python -m unittest discover -s tests` runs the test, passes, no network.

### E2 [x] Fix missing await in get_airfields_icao
Files: eaip/__init__.py, one new test file. Add the await. Test offline by patching the version lookup.
Do not: change anything else in that function.
Check: unit tests pass offline.
Read: OVERVIEW

### E3 [x] Compute the AIRAC date instead of probing — probe left in place; arithmetic added but not wired in
Human prerequisite: note one known AIRAC effective date from the eAIP index page and give it to the task.
Files: eaip/__init__.py, tests. Replace the ~30-request probe with date arithmetic (28-day cycles from the given epoch).
Keep an explicit eaip_date override. At most one confirming request, only when run live.
Check: offline tests of the date function for several dates around cycle boundaries.
Read: OVERVIEW

### E4 [x] ENR-2.1 table to raw records — 419 records (incl. BRIZE, row_id None); vertical limits as `bands` list
Human prerequisite: tests/fixtures/EG-ENR-2.1.html saved (the CTA/CTR/TMA page).
Files: new eaip/enr21.py, new tests. Parse the table into records: name, class, upper/lower limit text,
raw boundary text, frequency/callsign, remarks. No geometry yet.
Check: test asserts the record count and three named records against the fixture.
Read: OVERVIEW

### E5 [ ] Boundary geometry
Files: eaip/airspace/lateral/*.py, new tests. Fix Line.end (segment position, not type ordinal).
Parse boundary text from E4 into a closed list of {lat,lng}, expanding arcs and circles. Compare approach with
caa-map/airspace.py (read-only reference). Do not edit caa-map.
Check: tests for a multi-segment boundary with an arc; first and last points equal; area looks sane.
Read: OVERVIEW

### E6 [ ] ENR-5.1 danger, prohibited, restricted areas
Human prerequisite: tests/fixtures/EG-ENR-5.1.html. Reuse E4/E5 code. Output: name, ident, limits, boundary.

### E7 [ ] ENR-4.1 navaids
Human prerequisite: tests/fixtures/EG-ENR-4.1.html. Output: id, name, type, frequency, dme, location, variation if listed.

### E8 [ ] JSON export in caa-map schema
Files: new eaip/export.py, new tests. One function per caa-map file in the contract. Before writing, inspect the existing
caa-map JSON files read-only (head -c 500) and copy the exact keys and value formats.
Check: exported output for the fixtures has the same keys and types as the existing files.

### E9 [ ] Investigate MATZ and VRP sources
Research only, no code: report where MATZ and VRPs are published and whether NATS eAIP has them.

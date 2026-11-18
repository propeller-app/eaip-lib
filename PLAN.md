# eaip-lib plan
Goal: extract everything caa-map needs from the NATS eAIP and export it as JSON in caa-map's schema
(see ../PLAN.md data contract). Tasks are small and independent. One per session.
Fixtures are saved eAIP pages in tests/fixtures/. The human saves them; never fetch from the network.

## Known issues
- Line.end bug in legacy eaip/airspace/lateral/; superseded by boundary.py; E5c should switch airfield.py to boundary.py and delete the legacy classes
- get_airfields_icao misses an await when eaip_date is None
- Latest-release discovery fires ~30 concurrent requests
- tests/airfield.py hits the live site and is not found by unittest discovery
- Pickle cache at ~/.cache/eaip-lib can break across code changes; no expiry
- ppr is hardcoded False
- Exclusions that live in remarks, not boundary_text: BELFAST TMA 1 ('But excluding the Belfast CTR'), BRIZE NORTON CTR ('excluding any Airspace which is within the ATZ of Oxford Aerodrome'). exclusions is therefore incomplete until E8 decides whether to carry remarks across as a free-text note or turn them into exclusions entries.
- L975 Crossing Area remarks (fixture lines 14843, 14878, 14920) say 'bounded by straight lines joining ...'; check in E6 or E8 whether these records describe a different shape.

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

### E5a [x] Boundary geometry: vertices, arcs, latitude lines
Files: new eaip/airspace/boundary.py, new tests/test_boundary.py. Parse E4 boundary_text into a closed list of
{lat,lng} with stdlib math only: vertices, clockwise/anti-clockwise arcs (stated radius, 3 degree step),
lines of latitude (0.5 degree step), optional labels after vertices, "to -". Raise BoundaryError on anything else.
Check: 416/419 parse; only LONDON UIR, SCOTTISH UIR and LONDON GATWICK CTA fail; arcs cross north both ways.

### E5b [x] Boundary geometry: exclusions and same-extent references
Files: eaip/airspace/boundary.py, tests. Handle the "but excluding" sentence (LONDON GATWICK CTA) and resolve
"Same extent as" (LONDON UIR, SCOTTISH UIR). Daventry record if still failing.

### E5c [ ] ATZ boundaries from AD 2.17
Files: eaip/airspace/boundary.py, eaip/airfield.py, tests. Parse AD 2.17 ATZ text with the same parser.
Compass-worded arcs ("thence south/north by the arc") must be resolved by matching the word to the arc's
initial tangent (direction of travel at the arc start), NOT by mapping south/north to clockwise; Redhill ATZ
in tests/fixtures/EG-AD-2.EGKR.html is the test case.
Check: Redhill ATZ parses, closes, stays within 0.1 NM of 2 NM, and its clockwise sweep is monotonic.

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

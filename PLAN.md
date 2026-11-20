# eaip-lib plan
Goal: extract everything caa-map needs from the NATS eAIP and export it as JSON in caa-map's schema
(see ../PLAN.md data contract). Tasks are small and independent. One per session.
Fixtures are saved eAIP pages in tests/fixtures/. The human saves them; never fetch from the network.

## Known issues
- Line.end bug in legacy eaip/airspace/lateral/; superseded by boundary.py; E5c should switch airfield.py to boundary.py and delete the legacy classes
- Latest-release discovery fires ~30 concurrent requests
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

### E3b [ ] Wire AIRAC arithmetic into latest-release discovery: use airac_effective_date/next_airac_date, keep the eaip_date override, at most one confirming request when run live, remove the ~30-request probe

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

### E6a [x] ENR-5.1 danger, prohibited, restricted areas: raw records
Files: new eaip/enr51.py, new tests/test_enr51.py.
Human prerequisite: tests/fixtures/EG-ENR-5.1.html. Parse the single ENR-5.1 table into 1307 raw records:
ident/name from the TAIRSPACE;CODE_ID + TAIRSPACE;TXT_NAME pair, section from the dividers
(Danger 446, Prohibited 2, Restricted 859), boundary_text as printed (unparsed), limits from the
hidden TAIRSPACE_VOLUME tags (VAL/UOM/CODE upper/lower plus ANNOTATION, absent parts None),
remarks and activation. Dividers and header rows are not records. No geometry, no network.
Check: 1307 records, unique idents, section counts, six named records (incl. EGR157's 5 arcs),
EGR1U001A's 2000 FT AGL, 211 circles, 7 M/FT circles, 147 latitude records, and the raw
EGD012 coastline phrase and EGR160 Thames exclusion.

### E6b [x] ENR-5.1 geometry — 1307/1307 parsed (1096 polygons, 211 circles, 7 coastline chords flagged approximate, EGR160 exclusion); ENR-2.1 419/419 unchanged
Files: eaip/enr51.py, eaip/airspace/boundary.py, tests.
Parse each boundary_text into a closed boundary with E5a/E5b code; add circle support and check areas.
Do not subtract exclusions or follow natural features. Decisions:
1. Lines of latitude: reuse boundary.py's existing parallel handling.
2. Non-NM circles (7): convert the radius to NM internally (1 m = 1/1852 NM, 1 ft = 0.3048 m);
   keep the printed radius and unit in the result.
3. Thames sentence (EGR160): treat any trailing sentence starting "Excluding ..." as an exclusions
   note with no geometry subtracted, the same rule as "but excluding" in E5b.
4. Coastline/river phrases (6 records, 7 phrases: EGD012, EGD031, EGD138D, EGD401, EGD710 x2,
   EGD802): draw straight chords between the printed endpoints, flag each affected record as
   approximate, and keep the printed feature phrase in an "approximations" list. Never silent;
   E8 decides whether to export flagged records.
5. Circle wording: circles say "centred at", arcs say "centred on"; accept each only where it appears.

### E7 [x] ENR-4.1 navaids
Human prerequisite: tests/fixtures/EG-ENR-4.1.html. Output: id, name, type, frequency, dme, location, variation if listed.
Done: `eaip.enr41.parse_enr41` returns 54 raw records (20 VOR/DME, 1 VOR, 31 DME, 2 NDB); suite 91/91.

### E8a [x] ENR-2.1 JSON export (ctas.json, ctrs.json, tma.json)
Files: new eaip/export.py, new tests/test_export_airspace.py. Writes one entry per band, routes by name keyword, skips FIR/UIR/OCA.
Done: `eaip.export.write_airspace_files` writes 382 CTA, 1 CTR and 39 TMA entries (422 total) plus 6 skipped records; suite 103/103.

### E8b [ ] JSON export: danger and navaids
Files: extend eaip/export.py, tests. danger.json: export 1035 records whose upper limit has digits (ALT 315, AGL 661, FL 59), limits as printed with 'FL 195' -> 'FL195'; the 272 UNL/AUP records go to danger_skipped.json with reason; extra keys section, approximate (bool), source; follow-up task in caa-map to make the renderer handle AGL/FL/UNL/AUP. vors.json: only the 21 rows with a VOR component (20 VOR/DME + PTH); id, location, frequency as str(value) e.g. '114.3', dme = 'DME' in components, rotation = -(declination if present else magnetic_variation) with the sign in one constant; sanity-check CPT and BIG against the old file.

### E9 [ ] Investigate MATZ and VRP sources
Research only, no code: report where MATZ and VRPs are published and whether NATS eAIP has them.

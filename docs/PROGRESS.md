# PROGRESS

## 2026-11-15
- Done: Added docs/OVERVIEW.md (read-only repo overview: entry points, per-file summary, public API, extracted data/schema, fetching/caching, Python 3.14 risks, tests).
- Next: Implement ENR-2.1 standalone airspace extraction (`EAIP_AIRSPACES_URL` is defined but unused).
- Issues: `get_airfields_icao` misses `await` on `__get_current_version()` when `eaip_date=None`; `Line.end` uses wrong index; latest-release discovery fires ~30 concurrent requests (impolite); test hits live network.

## 2026-11-18
- Done: E1 complete. `tests/airfield.py` -> `tests/test_airfield.py` (unittest, sync, no network); parses `tests/fixtures/EG-AD-2.EGKR.html` via `get_airfield_from_raw_html(html, datetime.datetime(2026, 1, 22))` and asserts icao EGKR, name Redhill, ARP 51.213611/-0.138611 (delta 0.01), >=1 runway, >=1 radio. `unittest discover` passes 5/5, also passes with sockets/DNS blocked.
- Next: E2 (missing `await` in `get_airfields_icao`).
- Issues: fixture is ignored by `.gitignore` (blanket `*.html`, added at line 41) and by `.ignore`, so it needs `git add -f`; PLAN E1's "fixed date string" is actually a `datetime.datetime` (a str raises `AttributeError` in `get_formatted_date`).
- Issues (pre-existing, not E1): `RadioFrequency.frequency` raises `AttributeError: 'NoneType'` on one EGKR 2.18 row (`(\d{3}\.\d{3}) MHz` doesn't match its data[2]); 2.12 parses six designations (07L/25R/07R/25L/18/36) from the fixture.

## 2026-11-18 (E2)
- Done: added the missing `await` at `eaip/__init__.py:104` (`eaip_date = await __get_current_version()`); one line, nothing else in the module touched.
- Done: new `tests/test_airfields_icao.py` (``IsolatedAsyncioTestCase``, `eaip_date=None`): patches `eaip.__get_current_version` with an `AsyncMock` returning `datetime.datetime(2026, 1, 22)` and `eaip.aiohttp.ClientSession` with a fake async-CM returning a 2-entry EGKR/EGLL menu snippet; asserts one await, URL uses `2026-01-22`, and the ICAO list. Failed with `AttributeError: 'coroutine' object has no attribute 'strftime'` before the fix, passes after.
- Next: E3 (compute the AIRAC date instead of probing).
- Issues: `unittest discover` now 7/7 OK, and 7/7 OK with `socket.connect`/`connect_ex`/`create_connection`/`getaddrinfo` raising. Test double lives in `tests/`, no fixtures added, no network.

## 2026-11-18 (E3, modified by human)
- Done: added `EAIP_AIRAC_EPOCH = datetime.datetime(2026, 10, 29)`, `EAIP_AIRAC_CYCLE_DAYS = 28`, and pure `airac_effective_date(on)` / `next_airac_date(on)` (floor division on days since epoch, so pre-epoch dates work; naive midnight `datetime.datetime`; `None` defaults to `date.today()` only at the edge). Additions only — probe and its callers untouched, nothing wired in.
- Done: `tests/test_airac.py` (10 tests) covers epoch, +/-1 day, the full 2026 sequence (01-22 ... 12-24), the 2026/2027 boundary, pre-epoch dates incl. 2026-01-22 and 2026-01-21, date==datetime inputs, and naive-midnight return.
- Result: `unittest discover` 17/17 OK; 17/17 also with sockets/DNS blocked. New tests failed with `AttributeError: module 'eaip' has no attribute 'airac_effective_date'` before implementation.
- Issues: PLAN E3 still says "replace the ~30-request probe", which contradicts the human's modification; probe remains, so E3's original acceptance is only partly met. `.gitignore` still force-adds fixtures.

## 2026-11-18 (E4)
- Done: new `eaip/enr21.py` with pure `parse_enr21(html) -> list[dict]`: 419 records (418 main table + BRIZE NORTON CTR from the ENR-2.1.1 table, `row_id` None). Fields: row_id, name, boundary_text (raw, unparsed, incl. "Same extent as ..."), bands (list of {upper, lower, minimum, class}; 12 records have 2 bands), units ({name, callsign, language, hours, frequencies}), remarks (`<br>` -> `\n`).
- Done: `tests/test_enr21.py` (10 tests) passes; `unittest discover` 27/27 and 27/27 with sockets/DNS blocked. Failed with ImportError before the module existed.
- Values verified from fixture: BERRY HEAD CTA 6 (1490/1494-1497/1500-1514/1518), COTSWOLD CTA 11 (4264/4268-4271/4274-4291 + 1020_700 4297-4313), LONDON UIR (570/572/573-576/579-615), PEPZE CTA 9 (11028/11041/11044), BRIZE (16816/16817/16818/16823-16827).
- Issues: BRIZE frequency text keeps its "MHz" suffix ("119.005 MHz") and BRIZE's callsign cell has bare-text language/hours — E8 must normalise both; `TFREQUENCY;ANNOTATION` text is excluded from `frequencies` (kept nowhere yet).

## 2026-11-18 (E5a)
- Done: new `eaip/airspace/boundary.py` with pure `parse_boundary(text) -> [{lat,lng}]` and `parse_boundaries(records) -> (parsed, failed)`: vertices, clockwise/anti-clockwise arcs (stated radius, <=3 deg step, endpoints exact), lines of latitude (<=0.5 deg longitude step), optional `(label)` after a vertex, `to -`, `- thence`, `centred`/`centered`; refuses anything else with `BoundaryError` naming the fragment. Stdlib `math` only.
- Done: `tests/test_boundary.py` (18 tests) covers coordinate conversion, BERRY HEAD CTA 6 (5 points), BRIZE (decimal 5.5 NM, "centered"), LONDON TMA 1 0.9 deg sliver, real north-crossing arcs (ABERDEEN CTA 1 cw, EDINBURGH CTA 2 acw), four synthetic north/cardinal arcs, Daventry label, LONDON FIR latitude densification, and the 419-record run.
- Result: 416/419 parse; expected failures only LONDON UIR, SCOTTISH UIR (Same extent) and LONDON GATWICK CTA ("but excluding the Gatwick CTR."). `unittest discover` 45/45 OK, and 45/45 with sockets/DNS blocked. New test failed with ModuleNotFoundError before the module existed.
- Areas (spherical, report only): BRIZE NORTON CTR 131.8 sq NM, BERRY HEAD CTA 6 591.4 sq NM.
- Issues: compass-worded arcs ("thence south/north") are deliberately out of scope (E5c, tangent rule, Redhill test); legacy `Line.end`/lateral classes untouched and marked superseded in PLAN Known issues.

## 2026-11-18 (E5b)
- Done: `parse_boundaries` now returns `{name, points, exclusions, origin}` per record. A trailing `but excluding the <X>.` is stripped before parsing and recorded in `exclusions` (no geometry subtracted); `Same extent as <NAME>` copies the target's points, records the sentence in `origin`, and resolves chains/missing/failed targets into `failed` with named messages. `parse_boundary` itself is unchanged and still strict.
- Result: all 419 records parsed, 0 failed; only LONDON GATWICK CTA has `exclusions == ['Gatwick CTR']`; LONDON UIR points == LONDON FIR, SCOTTISH UIR == SCOTTISH FIR; every record closed. Prose scan of all 419 `boundary_text` found `excluding` only in Gatwick; `except`/`within`/`bounded by`/`including` had zero hits.
- Tests: 23 boundary tests (5 new: all-records 419/0, missing target, failed target, chain, general exclusion rule + end-anchored rejection) and 50/50 suite OK, also 50/50 with sockets/DNS blocked. New tests failed first (3 failures) before implementation.
- Issues: remark-only exclusions (BELFAST TMA 1, BRIZE NORTON CTR) remain unread and are recorded in PLAN Known issues; L975 "bounded by" remarks flagged for E6/E8.

## 2026-11-19 (E6a)
- Done: new `eaip/enr51.py` with `parse_enr51(html) -> list[dict]`: 1307 records (446 Danger / 2 Prohibited / 859 Restricted). Fields: `row_id`, `ident`, `name`, `section`, `boundary_text` (raw, whitespace-normalised), `limits` (`{'upper', 'lower'}`, each `{value, uom, code, annotation, text}` from the hidden TAIRSPACE_VOLUME tags), `remarks` (`<br>` -> `\n`), `activation` (TAIRSPACE_ACTIVATION texts). Dividers/header rows skipped; identity is the CODE_ID/TXT_NAME pair, never `row_id`.
- Done: `tests/test_enr51.py` (13 tests): 1307 records, unique stripped idents, section counts, field-by-field EGD001 (33) / EGD005B (136) / EGD005A (123) / EGD003Z1 (61) / EGD714BZ1 (5519) / EGR157 (6155, 5 arcs), EGR1U001A (6580, upper 2000 FT AGL at 6583), 211 circles / 7 M-FT circles / 147 latitude records, EGD012 (583) coastline phrase, EGR160 (6191/6193) Thames sentence. Failed with ModuleNotFoundError first, passes now.
- Result: `uv run python -m unittest discover -s tests` 63/63 OK; 63/63 with sockets/DNS blocked (throwaway `/tmp/opencode/no_net_runner.py`).
- Next: E6b geometry, per PLAN decisions 1-5 (latitude reuse, M/FT -> NM circles keeping printed radius/unit, trailing `Excluding ...` as an exclusion note, coastline/river chords flagged approximate in an `approximations` list, circles "centred at" vs arcs "centred on").
- Issues: `boundary_text` keeps 156 records outside the three grammars (147 latitude, 6 coastline/river, 7 M/FT circles, 1 Thames exclusion; 5 overlap), deliberately unparsed in E6a; E6b must handle or flag them.

## 2026-11-19 (E6b)
- Done: added public `circle_points(centre, radius_nm)` to `eaip/airspace/boundary.py`: 120 clockwise 3-degree segments from due north, 121 points, last point an exact copy of the first. No existing function changed.
- Done: new `parse_enr51_boundary(text)` and `parse_enr51_boundaries(records)` in `eaip/enr51.py`. Order: trailing `Excluding ...` -> exclusion note (EGR160), strict `A circle, ...` -> ring (NM as printed, M/1852, FT*0.3048/1852, printed radius/unit kept), `then along ... to` -> straight chord plus printed phrase in `approximations`, then `parse_boundary`. Results keyed by ident; one `BoundaryError` goes to `failures` without stopping the rest.
- Result: 1307/1307 parsed, 0 failures: 1096 polygons, 211 circles. 6 records flagged approximate with 7 phrases (EGD012, EGD031, EGD138D, EGD401, EGD710 x2, EGD802); EGR160 has the Thames exclusion; all shapes closed; 1089 direct-parser results unchanged.
- Tests: 4 new `circle_points` tests in `tests/test_boundary.py` and 9 in new `tests/test_enr51_boundary.py`; suite now 76/76 OK, and 76/76 with sockets/DNS blocked. New tests failed with ImportError first.
- Areas (report only, sq NM): largest EGD901Z1 20595.5, EGD901 18037.4, EGD219HZ1 16217.2; smallest EGR1U094 0.0107, EGR1U091 0.0393, EGR7U006J 0.0413. PLAN E6b ticked, E3b added, the two already-fixed Known issues removed.

## 2026-11-19 (E7)
- Done: new `eaip/enr41.py` with `parse_enr41(html)` -> 54 raw records in document order: 20 VOR/DME, 1 VOR, 31 DME, 2 NDB. Own DMS/variation parsers; no shared-file changes. One record per printed row; VOR/DME kept as `components` (E8 may split).
- Done: `tests/test_enr41.py` (15 tests) covers counts, type/component totals, ADN/PTH/LON/HEN/BEN field values, 5 hours annotations, 21 declinations, 54 magnetic variations, and strict errors. Tests failed with ModuleNotFoundError first.
- Result: `uv run python -m unittest discover -s tests` 91/91 OK; 91/91 with sockets/DNS blocked via `/tmp/opencode/no_net_runner.py`.
- Issues: fixture contradicts two task notes: LON has 113 FT elevation (not None); PTH is the VOR-only row and has no DME channel. VOR/DME rows have no `VAL_GHOST_FREQ`; `paired_frequency` is only on DME-only rows. PLAN E7 ticked; E8 note added.

## 2026-11-20 (E8a)
- Done: new `eaip/export.py` with `export_airspaces(records, boundaries)` and `write_airspace_files(html, out_dir)`. Routes by name keyword (TMA/CTR/CTA; ambiguous raises), one entry per band with `band_index`, and FIR/UIR/OCA to `skipped_airspaces.json`. Entry keys: name, upper_limit, lower_limit, _class, frequency, squawk, boundary, band_index, frequencies, exclusions, source.
- Done: new `tests/test_export_airspace.py` (12 tests): 382 CTA / 1 CTR / 39 TMA / 6 skipped, 11-key shape, FL-spacing and limit regex, LONDON GATWICK CTA, NORTH SEA CTA 1 two-band duplicate boundary, LONDON TMA 1, temp-dir round trip, and strictness (ambiguous name, bad frequency, bad class, no frequency). Tests failed with ModuleNotFoundError first.
- Result: `uv run python -m unittest discover -s tests` 103/103 OK (91 before); 103/103 with sockets/DNS blocked. `write_airspace_files` run once to `out/`: ctas 450091 B, ctrs 2646 B, tma 46063 B, skipped 539 B. `out/` added to `.gitignore` (it was not ignored).
- Issues: BRIZE NORTON CTR prints frequencies with a " MHz" suffix ("119.005 MHz"), so the parser accepts an optional trailing MHz unit instead of failing the whole export; its first unit's first frequency is 119.005. LONDON GATWICK CTA's first frequency is 118.950, not the old hand-made 126.825. 176/419 records have more than one distinct frequency; every exported `squawk` is "". No duplicate names and no ambiguous keyword names; all 419 boundaries parsed. PLAN E8 split into E8a [x] and E8b [ ].

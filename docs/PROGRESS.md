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

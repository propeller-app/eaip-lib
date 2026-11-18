# eaip-lib Overview

## 1. Purpose and entry points

Python library that fetches and parses the NATS UK eAIP (Aeronautical Information Package).
Async via `aiohttp`/`aiofiles`, HTML parsing via BeautifulSoup, geo conversion via `geopy`.
It is the data source for the sibling `../caa-map` VFR chart project.

- Entry point: the `eaip` package (`eaip/__init__.py`); everything is `await eaip.get_airfield(...)` style.
- No CLI. Consumed as a library (installed via `pip install <git url>` / `setup.py`).
- Run with Python 3.14 via `uv run <cmd>` (repo rule); deps in `requirements.txt`.

## 2. Source files

| File | One line |
|---|---|
| `eaip/__init__.py` | HTTP fetching of eAIP pages (index/menu/AD-2), latest-release discovery, pickle file cache, airfield scraping entry points |
| `eaip/airfield.py` | `Airfield` object: ICAO, name, geog, hours, contacts, runways, radios, airspace, charts from AD-2 sections 2.1–2.24 |
| `eaip/runway.py` | `Runway`: designation, bearing, dimensions, surface, geog, elevation, PAPI, TORA/TODA/ASDA/LDA |
| `eaip/radio.py` | `RadioFrequency`: service designation, callsign, frequency (MHz), hours, remarks |
| `eaip/hours.py` | `OperatingHours`/`OperatingWeek` dataclasses + parser from eAIP hour strings (H24, Daylight, Mon-Fri 0900-1700, Summer/Winter) |
| `eaip/airspace/airspace.py` | `Airspace`: designation, lateral geometry, vertical limits, class, callsign, transition alt, hours, remarks |
| `eaip/airspace/geog.py` | `Geog` ABC: base for all geometry/vertical objects holding the regex match + parent airspace |
| `eaip/airspace/lateral/{line,arc,circle,parallel}.py` | `Line` (start/end DMS points), `Arc` (adds direction/radius/centre), `Circle` (radius/centre), `Parallel` (line of latitude) |
| `eaip/airspace/vertical/{altitude,level}.py` | `Altitude` (FT ALT/AGL), `Level` (SFC / FLxxx) |
| `tests/airfield.py` | Single unittest: fetches EGKR live from the eAIP and checks the ICAO code |

## 3. Public API

- `eaip.get_airfields_icao(eaip_date=None) -> List[str]` — ICAO codes from the eAIP menu page.
- `eaip.get_airfield(icao, eaip_date=None, bypass_cache=False) -> Airfield` — one airfield (cached).
- `eaip.get_airfields(eaip_date=None, bypass_cache=False) -> List[Airfield]` — all airfields (gathered).
- `eaip.get_airfields_iter(...) -> AsyncIterator[Airfield]` — async iterator equivalent.
- `eaip.get_airfield_from_raw_html(html, eaip_date) -> Airfield` — parse saved HTML offline (fixture-friendly).
- `eaip.get_formatted_date(dt) -> str` — `%Y-%m-%d` used in eAIP URLs.
- Object accessors are `cached_property`: `Airfield` → `icao, name, geog (lat, long decimal), opening_hours, contact_phone, contact_email, website, address, runways, radios, airspace, ppr, charts`; `Runway` → `designation, bearing (deg true), dimensions (m), surface_type, geog, elevation (ft), papi, tora/toda/asda/lda (m)`; `RadioFrequency` → `designation, callsign, frequency (MHz), operating_hours, remarks`; `Airspace` → `designation, lateral (Circle or [Line/Arc/Parallel]), vertical (upper, lower), class_, callsign, language, transition_alt (ft), operating_hours, remarks`; `OperatingHours` → `hours/summer: OperatingWeek (8 day slots of (time, time)), is_24_hr, is_daylight`.

## 4. Data extracted

Extracted (from AD-2 aerodrome pages, sections referenced by heading number):
airfield name/ICAO/geog (2.1–2.2), opening hours (2.3), contacts (2.2), runways (2.12),
declared distances (2.13), lighting/PAPI (2.14), radio frequencies (2.18), airspace served by
the airfield/ATZ etc. (2.17), chart PDF links (2.24).

Output schema: Python objects (dataclass/plain classes with `cached_property`), not JSON dicts.
`Airfield.data` keeps the raw per-heading dict: `{heading_number|heading: {heading_number, heading, data (table rows or None), raw (text), links}}`.
Coordinates are WGS84 parsed from DMS to decimal degrees (floats). Units: distances metres,
arc/circle radii nautical miles, altitudes/elevations feet, frequencies MHz.

Not yet extracted: ENR-2.1 (CTA/CTR/TMA as standalone airspace list — `EAIP_AIRSPACES_URL` is defined
but unused), navaids (VOR/DME/NDB), waypoints/VRPs, obstacles, danger/prohibited/restricted areas
(EG D/P/R), MATZ details beyond 2.17 rows, and the `ppr` flag (hardcoded `False`).

## 5. Fetching, caching, rate handling

- Base URLs: `https://www.aurora.nats.co.uk/htmlAIP/Publications/{YYYY-MM-DD}-AIRAC/html/...`
  (`index-en-GB.html`, `EG-menu-en-GB.html`, `EG-AD-2.{icao}-en-GB.html`, ENR-2.1 constant).
- Latest release discovery (`__get_current_version`) probes one HEAD-ish GET per day of the
  current month (~28–31 concurrent requests) until one returns 200 — this is bulk/unpolite and
  contradicts the repo rule of one request at a time.
- Cache: pickled `Airfield` objects written to `~/.cache/eaip-lib/{date}/{icao}.bin`;
  `bypass_cache=True` refetches. No expiry; no rate limiting, no retries.

## 6. Python 3.14 risks

- `typing.List/Union/Awaitable/AsyncIterator` and `typing.Tuple[...]` annotations still work but
  are legacy; prefer builtins gradually (not required).
- `asyncio.as_completed` with pre-created `asyncio.Task` list (used twice) is fine, but the manual
  `req.cancel()` loop pattern is fragile on newer asyncio.
- `hours.py` builds `OperatingWeek(*hours[:8])` with tuples of possibly `None` — fine, but
  `(time.min, time.max)]*16` shares one tuple 16 times (aliasing, not a 3.14 break).
- `Line.end` indexes `airspace.lateral_lines[self.index + 1]`, but `index` is the regex-type
  ordinal (Line=0/Arc=1/Parallel=2), not the segment position — wrong for any boundary after the
  first (works only when all segments are `Line`).
- `get_airfields_icao` does `eaip_date = __get_current_version()` without `await` (line ~104),
  so `eaip_date=None` there yields a coroutine and `.strftime` would raise.
- geopy/aiohttp/bs4 versions must be 3.14-compatible; the pinned nothing (`requirements.txt`
  unpinned) means installs resolve against latest — re-verify after `uv add`.
- Pickle cache: unpickling cached objects across code changes can break `cached_property` classes.

## 7. Tests

- `tests/airfield.py` — unittest style, one test: `asyncio.run(eaip.get_airfield('EGKR'))` →
  asserts ICAO. It is an offline text using `get_airfield_from_raw_html`.
- No pytest config; the root `Makefile` is Sphinx-only. Run with:
  `uv run python -m unittest discover -s tests` (or `uv run python tests/airfield.py`).
- Sphinx docs build (`make -C docs html`) covers API docs via `docs/source`.

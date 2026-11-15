---
description: Read-only repo overview into docs/OVERVIEW.md
---
Read-only task. Only create docs/OVERVIEW.md; edit nothing else. Under 100 lines. Follow AGENTS.md.
Cover:
1. Purpose and entry points (how it is run)
2. One line per source file
3. Public API: main functions/classes, inputs, outputs
4. What eAIP data it extracts (airspace, airfields, navaids, obstacles, etc.), the output schema,
   and what is not yet extracted
5. How it fetches: URLs/endpoints, caching, rate handling, where files are written
6. Python 3.14 risks: deprecated APIs, anything likely to break
7. Tests: what exists, how to run them, whether they need the network

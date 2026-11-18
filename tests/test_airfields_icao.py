import datetime
import unittest
from unittest import mock

import eaip


MENU_HTML = """<html><body>
<div id="AD-2details">
  <div class="Hx"><a id="EGKRplus">EGKR</a></div>
  <div class="Hx"><a id="EGLLplus">EGLL</a></div>
</div>
</body></html>"""

EAIP_DATE = datetime.datetime(2026, 1, 22)


class _FakeResponse:
    """Stand-in for the menu page response (only ``text()`` is used)."""

    def __init__(self, html: str):
        self._html = html

    async def text(self) -> str:
        return self._html

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    """Stand-in for ``aiohttp.ClientSession`` that records requested URLs."""

    def __init__(self, requested_urls: list):
        self.requested_urls = requested_urls

    def get(self, url: str) -> _FakeResponse:
        self.requested_urls.append(url)
        return _FakeResponse(MENU_HTML)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class TestGetAirfieldsIcao(unittest.IsolatedAsyncioTestCase):
    """
    Exercises ``get_airfields_icao(eaip_date=None)`` fully offline: the
    version lookup and the HTTP client are both patched.
    """

    async def _call(self):
        requested_urls = []
        version_lookup = mock.AsyncMock(return_value=EAIP_DATE)
        with mock.patch.object(eaip, '__get_current_version', version_lookup):
            with mock.patch.object(eaip.aiohttp, 'ClientSession',
                                   side_effect=lambda: _FakeSession(requested_urls)):
                icaos = await eaip.get_airfields_icao(eaip_date=None)
        return icaos, requested_urls, version_lookup

    async def test_version_lookup_date_is_awaited(self):
        _, requested_urls, version_lookup = await self._call()
        # The lookup is async, so it must be awaited exactly once...
        self.assertEqual(version_lookup.await_count, 1)
        # ...and its datetime (not a coroutine object) must reach the URL.
        self.assertEqual(requested_urls,
                         [eaip.EAIP_MENU_URL.format('2026-01-22')])

    async def test_returns_icao_list_from_menu(self):
        icaos, _, _ = await self._call()
        self.assertEqual(icaos, ['EGKR', 'EGLL'])


if __name__ == '__main__':
    unittest.main()

import asyncio
import calendar
import datetime
import os
import pathlib
import pickle
import re
import typing

import aiofiles
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from eaip.airfield import Airfield

EAIP_INDEX_URL = 'https://www.aurora.nats.co.uk/htmlAIP/Publications/{0}-AIRAC/html/index-en-GB.html'
EAIP_MENU_URL = 'https://www.aurora.nats.co.uk/htmlAIP/Publications/{0}-AIRAC/html/eAIP/EG-menu-en-GB.html'
EAIP_AIRFIELD_URL = 'https://www.aurora.nats.co.uk/htmlAIP/Publications/{0}-AIRAC/html/eAIP/EG-AD-2.{1}-en-GB.html'

CACHE_DIRECTORY = os.path.join(pathlib.Path.home(), '.cache', 'eaip-lib')
"""
The directory where file-system cache is stored.
"""


async def __get_current_version() -> typing.Union[None, datetime.datetime]:
    """
    Attempts to discover the date for latest release of the eAIP.

    If release for current month is not found then this method
    will return ``None``.

    :return: Date of latest release.
    """
    year, month = datetime.datetime.now().year, datetime.datetime.now().month
    _, month_len = calendar.monthrange(year, month)

    async with aiohttp.ClientSession() as session:
        reqs = []
        for day in range(1, month_len + 1):
            day_of_month = datetime.datetime(year, month, day)
            eaip_date = day_of_month.strftime('%Y-%m-%d')
            url_format = EAIP_INDEX_URL.format(eaip_date)

            async def does_eaip_exist(d, url):
                async with session.get(url) as resp:
                    return d if resp.status == 200 else None
            reqs.append(asyncio.Task(does_eaip_exist(day_of_month, url_format)))

        for result_awaitable in asyncio.as_completed(reqs):
            result = await result_awaitable
            if result is not None:
                for req in reqs:
                    req.cancel()
                return result


async def __get_airfields_awaitable(eaip_date: datetime.datetime,
                                    bypass_cache: bool = False) -> typing.List[typing.Awaitable]:
    """
    Return list of awaitable that will yield Airfield objects eventually.

    :param eaip_date:  The date of eAIP release to scrape.
    :return: List of awaitable.
    """
    if eaip_date is None:
        eaip_date = await __get_current_version()

    eaip_airfields_icao = await get_airfields_icao(eaip_date)

    return [get_airfield(airfield_icao, eaip_date, bypass_cache) for airfield_icao in eaip_airfields_icao]


def get_formatted_date(eaip_date: datetime.datetime) -> str:
    """
    Formats :py:meth:`datetime.datetime` object for use in eAIP.

    Example:

    ::

        eaip.get_formatted_date(datetime.datetime(20, 12, 25))
        # Expected output: 2020-12-25

    :param eaip_date: ``datetime.datetime`` object to format.
    :return: The formatted date.
    """
    return eaip_date.strftime('%Y-%m-%d')


async def get_airfields_icao(eaip_date: datetime.datetime = None) -> typing.List[str]:
    """
    Returns ICAO codes for all Airfields in the eAIP.

    If ``eaip_date`` parameter is ``None`` then the latest eAIP is returned.

    :param eaip_date:  The date of eAIP release to scrape.
    :return: List of ICAO codes for airfields.
    """
    if eaip_date is None:
        eaip_date = __get_current_version()

    formatted_date = get_formatted_date(eaip_date)

    async with aiohttp.ClientSession() as session:
        async with session.get(EAIP_MENU_URL.format(formatted_date)) as resp:
            menu_content = await resp.text()
            soup = BeautifulSoup(menu_content, 'html.parser')
            menu_element = soup.find(id='AD-2details')
            menu_item_elements = menu_element.find_all('div', 'Hx', recursive=False)

            icao_list = [re.findall(r'.*(EG\w+)plus', next(menu_item.children).attrs['id'])[0]
                         for menu_item in menu_item_elements]
            return icao_list


def get_airfield_from_raw_html(html: str, eaip_date: datetime.datetime = None) -> Airfield:
    """
    Returns an airfield object representing eAIP html
    document passed in.

    :param html: The HTML document to parse.
    :param eaip_date: The date of eAIP release.
    :return: An airfield.
    """
    soup = BeautifulSoup(html, 'html.parser')
    airfield_element = soup.find(id=re.compile(r'AD-2\.EG\w{2}'))

    formatted_date = get_formatted_date(eaip_date)

    # Filter out junk that is irrelevant to API
    for div in airfield_element.find_all('span', {'class': ['sdParams', 'sdTooltip', 'AmdtDeletedAIRAC']}):
        div.decompose()

    airfield_raw_data = {}
    for item in airfield_element.find_all(id=re.compile(r'EG\w{2}-AD-\d+.\d'), recursive=False):
        title = item.find_all('h4', 'Title')[0]
        heading_number, heading = re.findall(r'.+AD\s(\d+.\d+)\s+(.+)', title.text)[0]

        airfield_datapoint_entry = {
            'heading_number': heading_number,
            'heading': heading,
            'data': {}
        }

        table = item.find_all('table', recursive=False)
        if table:
            table_data = [[re.sub(r'\n\s+', '\n', cell.text).strip()
                           for cell in row('td')] for row in table[0]('tr')]
            airfield_datapoint_entry['data'] = table_data
        else:
            airfield_datapoint_entry['data'] = None

        airfield_datapoint_entry['raw'] = item.text
        airfield_datapoint_entry['links'] = [urljoin(EAIP_MENU_URL.format(formatted_date), link.get('href'))
                                             for link in item.find_all('a', attrs={'href': True})]
        airfield_raw_data[heading_number] = airfield_datapoint_entry
        airfield_raw_data[heading] = airfield_datapoint_entry

    return Airfield(airfield_raw_data)


async def get_airfield(airfield_icao: str = None, eaip_date: datetime.datetime = None,
                       bypass_cache: bool = False) -> Airfield:
    """
    Scrapes eAIP for specific airfield and returns an
    airfield object representing requested airfield.

    If ``eaip_date`` parameter is ``None`` then the latest eAIP is returned.

    If ``bypass_cache`` parameter is set to ``True`` then the file-system
    cache is ignored, and the live version of eAIP is guaranteed to be
    pulled.

    Example:

    ::

        airfield = await get_airfield('EGKR')
        print(airfield.icao)

    :param eaip_date: The date of eAIP release to scrape.
    :param airfield_icao: The ICAO code of the airfield to return an object for.
    :param bypass_cache: Ignore the built-in cache.
    :return: An airfield object.
    """
    if eaip_date is None:
        eaip_date = await __get_current_version()

    formatted_date = get_formatted_date(eaip_date)

    cache_dir = os.path.join(CACHE_DIRECTORY, formatted_date)
    cache_url = os.path.join(cache_dir, f'{airfield_icao}.bin')

    if not bypass_cache:
        if not os.path.isdir(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)

        if os.path.exists(cache_url):
            with open(cache_url, 'rb') as cache:
                return pickle.loads(cache.read())

    async with aiohttp.ClientSession() as session:
        async with session.get(EAIP_AIRFIELD_URL.format(formatted_date, airfield_icao)) as resp:
            airfield_content = await resp.text()
            a = get_airfield_from_raw_html(airfield_content, eaip_date)

            async with aiofiles.open(cache_url, 'wb') as cache:
                await cache.write(pickle.dumps(a))
            return a


async def get_airfields(eaip_date: datetime.datetime = None, bypass_cache: bool = False) -> typing.List[Airfield]:
    """
    Gets all the Airfields in the eAIP, represented by Airfield
    objects.

    If ``eaip_date`` parameter is ``None`` then the latest eAIP is returned.

    Example:

    ::

        airfields = await eaip.get_airfields()
        for airfield in airfields:
          print(airfield.icao)

    :param eaip_date: The date of eAIP release to scrape.
    :param bypass_cache: Ignore the built-in cache.
    :return: All Airfields in the eAIP.
    """
    return await asyncio.gather(*await __get_airfields_awaitable(eaip_date, bypass_cache))


async def get_airfields_iter(eaip_date: datetime.datetime = None,
                             bypass_cache: bool = False) -> typing.AsyncIterator[Airfield]:
    """
    Gets all Airfields in the eAIP as an async iterator.

    Iterable equivalent of :py:meth:`eaip.get_airfields`.

    Example:

    ::

        async for airfield in eaip.get_airfields_iter():
            print(airfield.icao)

    :param eaip_date: The date of eAIP release to scrape.
    :param bypass_cache: Ignore the built-in cache.
    :return: Iterable of Airfields.
    """
    if eaip_date is None:
        eaip_date = await __get_current_version()

    for task in asyncio.as_completed(await __get_airfields_awaitable(eaip_date, bypass_cache)):
        yield await task

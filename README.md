# eaip-lib

eaip-lib is a raw-python library used for accessing the [NATS eAIP (Aeronautical Information Package)](http://www.nats-uk.ead-it.com/public/index.php%3Foption=com_content&task=blogcategory&id=165&Itemid=3.html) via a clean, fast and efficient API.

The library is capable of searching for the most recent eAIP and then extracting data and providing access via a clean & powerful Python API. Alternatively the release date of any eAIP release can be provided.

Python3.8 & `asyncio` support is built-in.

File system caching built-in for rapid access to eAIP and reduced bandwidth.

## Installation

```sh
$ pip install https://github.com/propellor-app/eaip-lib.git#egg=eaip-lib
```

## Build the docs

```sh
$ sphinx-autodoc -o ./docs/source eaip
$ sphinx-build -b html ./docs/source ./docs/build
```

## Example Usage

Print all Airfields ICAO code and their runways from most recent eAIP.

```python
import asyncio, eaip

async def main():
    async for airfield in eaip.get_airfields_iter():
        print({
            'icao': airfield.icao,
            'runways': airfield.runways
        })

if __name__ == '__main__':
    asyncio.run(main())
```

Get Airfield radios with ICAO code `EGKK` (Gatwick) from eAIP release 10/09/2020.

```python
import asyncio, eaip, datetime

async def main():
    airfield = await eaip.get_airfield('EGKK', datetime.datetime(2020, 10, 9))
    print(airfield.radios)

if __name__ == '__main__':
    asyncio.run(main())
```
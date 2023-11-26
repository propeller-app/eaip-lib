import re
import typing
from functools import cached_property

from geopy.point import Point

from eaip.hours import OperatingHours, get_operating_hours_from_string
from eaip.radio import RadioFrequency
from eaip.runway import Runway
from eaip.airspace import Airspace


class Airfield:
    """
    A object representation of an airfield returned from the eAIP.

    Normally created via :py:meth:`eaip.get_airfield`, :py:meth:`eaip.get_airfields`
    or :py:meth:`eaip.get_airfields_iter`.

    Example to print ICAO code for every Airfield in the eAIP:

    ::

        async for airfield aeip.get_airfields_iter():
            print(airfield.icao)
    """

    icao: str
    name: str
    geog: typing.Tuple[float, float]
    opening_hours: typing.Union[None, OperatingHours]
    contact_phone: typing.List[typing.Tuple[str, str, str]]
    contact_email: typing.List[typing.Tuple[str, str]]
    website: typing.Union[None, str]
    address: typing.Union[None, str]
    runways: typing.List[Runway]
    runways_by_designation: typing.Dict[str, Runway]
    radios: typing.List[RadioFrequency]
    radios_by_designation: typing.Dict[str, typing.List[RadioFrequency]]
    ppr: bool

    def __init__(self, data: dict):
        self.data = data

    @cached_property
    def icao(self) -> str:
        """
        Airfield ICAO code.
        """
        return self.data['2.1']['raw'].strip()[0:4]

    @cached_property
    def name(self) -> str:
        """
        Full name of Airfield.
        """
        return re.findall(r'—\s+([\w /]+)', self.data['2.1']['raw'])[0].title()

    @cached_property
    def geog(self) -> typing.Tuple[float, float]:
        """
        Latitude and longitude of Airfield in decimal.
        """
        lat_deg, lat_min, lat_sec, lat_dir = re.findall(r'Lat: (\d{2})(\d{2})(\d{2})([NS])',
                                                        self.data['2.2']['data'][0][2])[0]
        long_deg, long_min, long_sec, long_dir = re.findall(r'Long: (\d{3})(\d{2})(\d{2})([EW])',
                                                            self.data['2.2']['data'][0][2])[0]
        lat = Point.parse_degrees(lat_deg, lat_min, lat_sec, direction=lat_dir)
        long = Point.parse_degrees(long_deg, long_min, long_sec, direction=long_dir)
        return lat, long

    @cached_property
    def opening_hours(self) -> typing.Union[None, OperatingHours]:
        """
        Represents the opening hours for this Airfield.
        """
        for row in self.data['2.3']['data']:
            if row[1] == 'AD Administration':
                return get_operating_hours_from_string(row[2])
        return None

    @cached_property
    def contact_phone(self) -> typing.List[typing.Tuple[str, str, str]]:
        """
        A list of contact phone numbers along with description and extension (if applicable).
        """
        for row in self.data['2.2']['data']:
            if row[1] == 'Telephone':
                contact_phone_raw = re.findall(r'([\d\- ]+\d)(?: Ext (\d+))?(?: \((.+)\))?', row[2])
                return [(
                    desc,
                    ''.join(filter(str.isdigit, number)),
                    ''.join(filter(str.isdigit, ext)))
                    for number, ext, desc in contact_phone_raw]
        return []

    @cached_property
    def contact_email(self) -> typing.List[typing.Tuple[str, str]]:
        """
        A list of contact email addresses along with description.
        """
        for row in self.data['2.2']['data']:
            if row[1] == 'E-mail address':
                contact_email_raw = re.findall(r'(\S+@\S+)(?: \((.+)\))?', row[2])
                return [(desc, email) for email, desc in contact_email_raw]
        return []

    @cached_property
    def website(self) -> typing.Union[None, str]:
        """
        A website address for the Airfield.
        """
        for row in self.data['2.2']['data']:
            if row[1] == 'Web address':
                return row[2]
        return None

    @cached_property
    def address(self) -> typing.Union[None, str]:
        """
        Address for airfield.
        """
        for row in self.data['2.2']['data']:
            if row[1] == 'Address':
                return row[2]
        return None

    @cached_property
    def runways(self) -> typing.List[Runway]:
        """
        A list of runways belonging to this Airfield.
        """
        return list(self.runways_by_designation.values())

    @cached_property
    def runways_by_designation(self) -> typing.Dict[str, Runway]:
        """
        A dict of runways, indexed by designation.
        """
        runways = {}
        for row in self.data['2.12']['data'][2:]:
            r = Runway(self, row)
            runways[r.designation] = r
        return runways

    @cached_property
    def radios(self) -> typing.List[RadioFrequency]:
        """
        A list of radio frequencies.
        """
        return [radio_fq for designation in self.radios_by_designation.values() for radio_fq in designation]

    @cached_property
    def radios_by_designation(self) -> typing.Dict[str, typing.List[RadioFrequency]]:
        """
        A dict of radio frequencies, indexed by designation.
        """
        rfs = {}
        if self.data['2.18']['data']:
            for row in self.data['2.18']['data'][2:]:
                if len(row) == 7:
                    rf = RadioFrequency(self, row)
                    rfi = rfs.get(rf.designation, [])
                    rfi.append(rf)
                    rfs[rf.designation] = rfi
        return rfs

    @cached_property
    def airspace(self) -> typing.List[Airspace]:
        """
        A list of Airspace objects.
        """
        if self.data['2.17']['data']:
            return [
                Airspace(self, row)
                for row in self.data['2.17']['data'][2:]
                if len(row) == 7
            ]
        return []

    @cached_property
    def ppr(self) -> bool:
        """
        Does airfield have PPR.
        """
        return False

    @cached_property
    def charts(self) -> typing.Union[None, typing.List[typing.Tuple[str, str]]]:
        """
        A list of PDF charts for this airfield stored as tuple (Chart Title, Chart URL).
        """
        if self.data['2.24']['data']:
            return [(self.data['2.24']['data'][x][0], self.data['2.24']['links'][i])
                    for i, x in enumerate(range(0, len(self.data['2.24']['data']), 2))]
        return None

    def __repr__(self):
        return f'Airfield(icao={self.icao}, name={self.name})'

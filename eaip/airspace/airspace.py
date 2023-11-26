import re
import typing
from functools import cached_property

import eaip
from eaip.hours import OperatingHours, get_operating_hours_from_string
from eaip.airspace.geog import Geog
from eaip.airspace.lateral import Arc, Line, Parallel, Circle
from eaip.airspace.vertical import Altitude, Level

class Airspace:
    """
    Object that represents airspace including
    the lateral and vertical limits.
    """

    designation: str
    lateral: typing.List[Geog]
    vertical: str
    class_: str
    callsign: str
    language: str
    transition_alt: typing.Union[None, int]
    operating_hours: typing.Union[None, OperatingHours]
    remarks: str
    data: typing.List[str]

    def __init__(
        self,
        airfield: typing.Union[None, 'eaip.airfield.Airfield'],
        data: typing.List[str]
    ):
        self.airfield = airfield
        self.data = data

    @cached_property
    def designation(self) -> str:
        """
        Airspace designation.
        """
        return self.data[0].split('\n', 1)[0]

    @cached_property
    def lateral(self) -> typing.Union[typing.List[Line],Circle]:
        """
        Either a Circle object or a list of Line objects
        representing the lateral airspace.
        """
        return self.lateral_circle if self.lateral_circle else self.lateral_lines

    @cached_property
    def lateral_circle(self) -> typing.Optional[Circle]:
        """
        A circle object representing the lateral
        airspace (Or None if not applicable).
        """
        descriptor = self.data[0].split('\n', 1)[1]
        match = re.search(
            r'^.+ circle.+(\d+(?:\.\d+)?) NM .+ '
            r'centred .+(\d{2})(\d{2})(\d{2})([NS]) '
            r'(\d{3})(\d{2})(\d{2})([EW])'
            r'(?: .+ \((\d+)\/(\d+)\))?.*$',
            descriptor
        )
        return Circle(match, self) if match is not None else None

    @cached_property
    def lateral_lines(self) -> typing.List[Line]:
        """
        List of line objects representing the lateral
        airspace (Empty if not applicable).
        """
        descriptors = self.data[0].split('\n', 1)[1].split(' - ')
        types_patterns = {
            Line: re.compile(
                r'^(\d{2})(\d{2})(\d{2})([NS]) '
                r'(\d{3})(\d{2})(\d{2})([EW])$'
            ),
            Arc: re.compile(
                r'^(\d{2})(\d{2})(\d{2})([NS]) '
                r'(\d{3})(\d{2})(\d{2})([EW]) '
                r'thence (clockwise|anti-clockwise) '
                r'.+arc.+ (\d+(?:\.\d+)?) NM '
                r'centred on '
                r'(\d{2})(\d{2})(\d{2})([NS]) '
                r'(\d{3})(\d{2})(\d{2})([EW]) to '
                r'(\d{2})(\d{2})(\d{2})([NS]) '
                r'(\d{3})(\d{2})(\d{2})([EW])$'
            ),
            Parallel: re.compile(
                r'^(\d{2})(\d{2})(\d{2})([NS]) '
                r'(\d{3})(\d{2})(\d{2})([EW])'
                r'.+line of latitude.+$'
            )
        }

        return [geog for geog in (
            next((
                geog(i, match, self)
                for i, (geog, match) in enumerate((t, p.search(d))
                for t, p in types_patterns.items()
                if p.search(d))
            ), None)
            for d in descriptors
        ) if geog is not None]

    @cached_property
    def vertical(self) -> typing.Tuple[typing.Union[Altitude,Level]]:
        """
        A tuple representing the vertical airspace. 

        In the form (upper limit, lower limit).
        """
        return (
            self.vertical_upper,
            self.vertical_lower
        )

    @cached_property
    def vertical_upper(self) -> typing.Union[Altitude,Level]:
        """
        An Altitude (FT) or Level (Flight-Level) object 
        representing the vertical upper airspace limit. 
        """
        limit = re.search(r'Upper limit: (.+)', self.data[1])[1]
        return self.__vertical_matcher(limit)

    @cached_property
    def vertical_lower(self) -> typing.Union[Altitude,Level]:
        """
        An Altitude (FT) or Level (Flight-Level) object 
        representing the lower upper airspace limit. 
        """
        limit = re.search(r'Lower limit: (.+)', self.data[1])[1]
        return self.__vertical_matcher(limit)

    def __vertical_matcher(self, data: str) -> typing.Union[Altitude,Level]:
        types_patterns = {
            Altitude: re.compile(r'^(\d+) FT (ALT|AGL)$'),
            Level: re.compile(r'^(?:(SFC|FL)(\d+)?)$')
        }

        return next((
            t(match, self)
            for t, match in ((t, p.search(data))
            for t, p in types_patterns.items()
            if p.search(data))
        ), None)

    @cached_property
    def class_(self) -> str:
        """
        Airspace Class.
        """
        return self.data[2]

    @cached_property
    def callsign(self) -> str:
        """
        ATS unit callsign.
        """
        return self.data[3].split('\n', 1)[0]

    @cached_property
    def language(self) -> str:
        """
        ATS unit language.
        """
        return self.data[3].split('\n', 1)[1]

    @cached_property
    def transition_alt(self) -> typing.Union[None, int]:
        """
        The transition altitude in feet.
        """
        altitude = re.findall(r'(\d+) FT', self.data[4])
        return int(altitude[0]) if altitude else None

    @cached_property
    def operating_hours(self) -> typing.Union[None, OperatingHours]:
        """
        Represents the applicable hours for this Airspace.
        """
        return get_operating_hours_from_string(self.data[5]) if self.data[5] else None

    @cached_property
    def remarks(self) -> str:
        """
        Airspace remarks.
        """
        return self.data[6]

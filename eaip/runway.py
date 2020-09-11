import re
import typing
from functools import cached_property

from geopy.point import Point

import eaip


class Runway:
    """
    An object representation of an airfield
    runway.
    """

    designation: str
    bearing: typing.Union[None, float]
    dimensions: typing.Tuple[int, int]
    surface_type: typing.Union[None, str]
    geog: typing.Union[None, typing.Tuple[float, float]]
    elevation: typing.Union[None, int]
    papi: typing.Union[None, str]
    distances: typing.Union[None, typing.List[int]]
    tora: typing.Union[None, typing.List[int]]
    toda: typing.Union[None, typing.List[int]]
    asda: typing.Union[None, typing.List[int]]
    lda: typing.Union[None, typing.List[int]]

    def __init__(self, airfield: 'eaip.airfield.Airfield', data: dict):
        self.airfield = airfield
        self.data = data

    @cached_property
    def designation(self) -> str:
        """
        The runway heading.
        """
        return self.data[0]

    @cached_property
    def bearing(self) -> typing.Union[None, float]:
        """
        The true heading. `None` if not available.
        """
        bearing = self.data[1]
        return float(bearing.replace('°', '')) if bearing else None

    @cached_property
    def dimensions(self) -> typing.Tuple[int, int]:
        """
        Dimensions of runway in metres. 0x0m if not available.
        """
        dimensions = self.data[2]
        dimensions = re.findall(r'(\d+)\s+x\s+(\d+)\s+M', dimensions.replace('-', '0'))
        return dimensions[0] if dimensions else (0, 0)

    @cached_property
    def surface_type(self) -> typing.Union[None, str]:
        """
        Description of runway surface type. `None` if not available.
        """
        surface_type = self.data[3]
        surface_type = re.findall(r'RWY surface: (.+)', surface_type)
        return surface_type[0] if surface_type else None

    @cached_property
    def geog(self) -> typing.Union[None, typing.Tuple[float, float]]:
        """
        Latitude and longitude of runway in decimal. `None` if not available.
        """
        geog = self.data[4]
        geog = re.findall(r'(\d{2})(\d{2})(\d{2}\.\d+)([NS]) (\d{3})(\d{2})(\d{2}\.\d+)([EW])', geog)

        if geog:
            lat_deg, lat_min, lat_sec, lat_dir, long_deg, long_min, long_sec, long_dir = geog[0]

            lat = Point.parse_degrees(lat_deg, lat_min, lat_sec, direction=lat_dir)
            long = Point.parse_degrees(long_deg, long_min, long_sec, direction=long_dir)
            return lat, long
        return None

    @cached_property
    def elevation(self) -> typing.Union[None, int]:
        """
        The threshold elevation of the runway in feet. ``None`` if not available.
        """
        elevation = self.data[5]
        elevation = re.findall(r'THR (\d+) FT', elevation)
        return int(elevation[0]) if elevation else None

    @cached_property
    def papi(self) -> typing.Union[None, str]:
        """
        The type of lighting on the runway.

        TODO: Perhaps return an object that contains more information about the lighting?
        """
        if self.airfield.data['2.14']['data']:
            for row in self.airfield.data['2.14']['data'][2:]:
                if row[0] == self.designation:
                    return row[3].partition('\n')[0] or None
        return None

    def distances(self, distance_short: str = 'TORA') -> typing.Union[None, typing.List[int]]:
        """
        Gets declared distances by type specified.

        Sorted highest to lowest.

        ``None`` if no distances information is available.

        :param distance_short: Type of distance to find.
        :return: The list of distances in metres.
        """
        distance_shorts = ['TORA', 'TODA', 'ASDA', 'LDA']
        distance_col = distance_shorts.index(distance_short) + 1
        distances = [re.search(r'(\d+) M', row[distance_col])
                     for row in self.airfield.data['2.13']['data'][2:]
                     if row[0] == self.designation]
        distances = [int(distance.group(1)) for distance in distances if distance is not None]
        distances.sort(reverse=True)
        return distances or None

    @cached_property
    def tora(self) -> typing.Union[None, typing.List[int]]:
        """
        Sorted highest to lowest.

        Syntactic sugar for ``self.distances('TORA')``.

        List of take off run available distances in metres.
        """
        return self.distances('TORA')

    @cached_property
    def toda(self) -> typing.Union[None, typing.List[int]]:
        """
        Sorted highest to lowest.

        Syntactic sugar for ``self.distances('TODA')``.

        List of take off distance available distances in metres.
        """
        return self.distances('TODA')

    @cached_property
    def asda(self) -> typing.Union[None, typing.List[int]]:
        """
        Sorted highest to lowest.

        Syntactic sugar for ``self.distances('ASDA')``.

        List of accelerate-stop distance available distances in metres.
        """
        return self.distances('ASDA')

    @cached_property
    def lda(self) -> typing.Union[None, typing.List[int]]:
        """
        Sorted highest to lowest.

        Syntactic sugar for ``self.distances('LDA')``.

        List of landing distance available distances in metres.
        """
        return self.distances('LDA')

    def __repr__(self):
        return f'Runway(designation={self.designation}, bearing={self.bearing})'

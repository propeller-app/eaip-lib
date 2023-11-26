import typing
from functools import cached_property
from geopy.point import Point

from eaip.airspace.geog import Geog

class Line(Geog):
    """
    Represents a line in an Airspace object
    """
    index: int
    start: typing.Tuple[float, float]
    end: typing.Tuple[float, float]

    def __init__(self, index, *args):
        super().__init__(*args)
        self.index = index

    @cached_property
    def start(self) -> typing.Tuple[float, float]:
        """
        Latitude and longitude of start point in decimal.
        """
        (lat_deg, lat_min, lat_sec, lat_dir) = self.data.groups()[0:4]
        (long_deg, long_min, long_sec, long_dir) = self.data.groups()[4:8]
        lat = Point.parse_degrees(lat_deg, lat_min, lat_sec, direction=lat_dir)
        long = Point.parse_degrees(long_deg, long_min, long_sec, direction=long_dir)
        return lat, long

    @cached_property
    def end(self) -> typing.Tuple[float, float]:
        """
        Latitude and longitude of end point in decimal.
        """
        return self.airspace.lateral_lines[self.index + 1].start

    def __repr__(self):
        return f'Line(start={self.start}, end={self.end})'

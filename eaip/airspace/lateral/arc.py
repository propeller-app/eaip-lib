import typing
from functools import cached_property
from enum import Enum
from geopy.point import Point
from eaip.airspace.lateral.line import Line

class Direction(Enum):
    """
    Direction enum (clockwise or anti-clockwise)
    """
    CLOCKWISE = 'clockwise'
    ANTI_CLOCKWISE = 'anti-clockwise'

class Arc(Line):
    """
    Represents an arc in an Airspace object
    """
    direction: Direction
    centre: typing.Tuple[float, float]
    radius: float

    @cached_property
    def direction(self) -> Direction:
        """
        The direction about which the arc point is drawn,
        will be either Direction.CLOCKWISE or Direction.ANTI_CLOCKWISE.
        """
        return Direction(self.data[9])

    @cached_property
    def radius(self) -> float:
        """
        Radius of the arc in nautical miles.
        """
        return float(self.data[10])

    @cached_property
    def centre(self) -> typing.Tuple[float, float]:
        """
        Latitude and longitude of the center point
        of the circle.
        """
        (lat_deg, lat_min, lat_sec, lat_dir) = self.data.groups()[10:14]
        (long_deg, long_min, long_sec, long_dir) = self.data.groups()[14:18]
        lat = Point.parse_degrees(lat_deg, lat_min, lat_sec, direction=lat_dir)
        long = Point.parse_degrees(long_deg, long_min, long_sec, direction=long_dir)
        return lat, long

    def __repr__(self):
        return f'Arc(start={self.start}, end={self.end})'

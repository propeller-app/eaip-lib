import typing
from functools import cached_property
from geopy.point import Point

from eaip.airspace.geog import Geog

class Circle(Geog):
    """
    Represents a circle in an Airspace object
    """

    radius: float
    centre: typing.Tuple[float, float]

    @cached_property
    def radius(self) -> float:
        """
        Radius of the arc in nautical miles.
        """
        return float(self.data[1])

    @cached_property
    def centre(self) -> typing.Tuple[float, float]:
        """
        Latitude and longitude of the center point
        of the circle.
        """
        (lat_deg, lat_min, lat_sec, lat_dir) = self.data.groups()[1:5]
        (long_deg, long_min, long_sec, long_dir) = self.data.groups()[5:9]
        lat = Point.parse_degrees(lat_deg, lat_min, lat_sec, direction=lat_dir)
        long = Point.parse_degrees(long_deg, long_min, long_sec, direction=long_dir)
        return lat, long

    def __repr__(self):
        return f'Circle(radius={self.radius}, centre={self.centre})'

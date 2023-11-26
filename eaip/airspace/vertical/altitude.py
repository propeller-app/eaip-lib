from functools import cached_property

from eaip.airspace.geog import Geog

class Altitude(Geog):
    """
    Represents altitude measurements
    in feet.
    """
    height: int
    above_ground_level: bool

    @cached_property
    def height(self) -> int:
        """
        Altitude in feet.
        """
        return int(self.data[1])

    @cached_property
    def above_ground_level(self) -> bool:
        """
        Indicates whether the measurement is
        above ground level.
        """
        return self.data[2] == 'AGL'

    def __repr__(self):
        return f'Altitude(height={self.height})'

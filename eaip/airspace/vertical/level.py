from functools import cached_property

from eaip.airspace.geog import Geog

class Level(Geog):
    """
    Represents altitude flight-level measurements.
    """
    height: int

    @cached_property
    def height(self) -> int:
        """
        Altitude in feet.
        """
        return int(0 if self.data[1] == 'SFC' else self.data[2])

    def __repr__(self):
        return f'Level(height={self.height})'

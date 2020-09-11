import re
import typing
from functools import cached_property

import eaip
from eaip.hours import OperatingHours, get_operating_hours_from_string


class RadioFrequency:
    """
    Object that represents radio frequencies for
    an airfield.
    """

    designation: str
    callsign: str
    frequency: float
    frequency_description: str
    operating_hours: typing.Union[None, OperatingHours]
    remarks: str

    def __init__(self, airfield: 'eaip.airfield.Airfield', data: dict):
        self.airfield = airfield
        self.data = data

    @cached_property
    def designation(self) -> str:
        """
        Service offered by radio facility.
        """
        designation = None
        for row in self.airfield.data['2.18']['data'][2:]:
            designation = row[0] if row[0] else designation
            if row == self.data:
                return designation

    @cached_property
    def callsign(self) -> str:
        """
        Radio callsign.
        """
        designation = None
        for row in self.airfield.data['2.18']['data'][2:]:
            designation = row[1] if row[1] else designation
            if row == self.data:
                return designation

    @cached_property
    def frequency(self) -> float:
        """
        Frequency of radio service in MHz.
        """
        return float(re.search(r'(\d{3}\.\d{3}) MHz', self.data[2]).group(1))

    @cached_property
    def frequency_description(self) -> str:
        """
        Frequency description.
        """
        return re.search(r'\d{3}\.\d{3} MHz(?:\n(.+))?', self.data[2]).group(1)

    @cached_property
    def operating_hours(self) -> typing.Union[None, OperatingHours]:
        """
        An OperatingHours object representing the operational hours of this radio service.
        """
        return get_operating_hours_from_string(self.data[5])

    @cached_property
    def remarks(self) -> str:
        """
        Radio frequency remarks as string.
        """
        return self.data[6]

    def __repr__(self):
        return f'RadioFrequency(designation={self.designation}, callsign={self.callsign}, frequency={self.frequency})'

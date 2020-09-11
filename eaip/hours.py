import datetime
import re
import typing
from dataclasses import dataclass


@dataclass
class OperatingWeek:

    monday: typing.Tuple[typing.List[datetime.time]]
    """
    Opening hours on Monday.
    """

    tuesday: typing.Tuple[typing.List[datetime.time]]
    """
    Opening hours on Tuesday.
    """

    wednesday: typing.Tuple[typing.List[datetime.time]]
    """
    Opening hours on Wednesday.
    """

    thursday: typing.Tuple[typing.List[datetime.time]]
    """
    Opening hours on Thursday.
    """

    friday: typing.Tuple[typing.List[datetime.time]]
    """
    Opening hours on Friday.
    """

    saturday: typing.Tuple[typing.List[datetime.time]]
    """
    Opening hours on Friday.
    """

    sunday: typing.Tuple[typing.List[datetime.time]]
    """
    Opening hours on Sunday.
    """

    holiday: typing.Tuple[typing.List[datetime.time]]
    """
    Opening hours on public holidays.
    """


class OperatingHours:
    """
    Object that represents the opening hours of an
    Airfield or the operating hours of any other type
    of object.
    """

    hours: OperatingWeek
    """
    Regular operating hours.
    """

    summer: OperatingWeek
    """
    Summer operating hours.
    """

    is_24_hr: bool
    """
    Is operating 24hr.
    """

    is_daylight: bool
    """
    Daylight-only operation.
    """

    def __init__(self, *hours: typing.Tuple[datetime.time, datetime.time],
                 is_24_hr: bool = False, is_daylight: bool = False):
        if is_24_hr:
            hours = [(datetime.time.min, datetime.time.max)]*15

        self.hours = OperatingWeek(*hours[:8])
        self.summer = OperatingWeek(*hours[8:16])
        self.is_24_hr = is_24_hr
        self.is_daylight = is_daylight

    def __repr__(self):
        return f'OperatingHours(is_24_hr={self.is_24_hr}, is_daylight={self.is_daylight})'


def get_operating_hours_from_string(string_to_convert: str) -> OperatingHours:
    """
    Converts a string representing operational hours or opening hours
    from the NATS eAIP into :py:meth:`eaip.hours.OperatingHours` object that provides datetime
    objects.

    :param string_to_convert: The string to decode.
    :return: The :py:meth:`eaip.hours.OperatingHours` object which represents the string.
    """
    opening_hours_raw = re.findall(
        r'(H24)|(Daylight).+|(Summer)|(Winter)|'
        r'(?:((?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|PH)'
        r'(?:-|, | & | and )?)+))|(\d{4}|SS)-(\d{4}|SS)|(\()|(\))',
        string_to_convert
    )

    opening_hours_raw = [data for sublist in opening_hours_raw for data in sublist]

    if len(opening_hours_raw) >= 2:
        is_24_hr, is_daylight = opening_hours_raw[:2]
        is_24_hr = is_24_hr == 'H24'
        is_daylight = is_daylight == 'Daylight'

        hours = [None] * 8
        summer_hours = [None] * 8

        is_summer = False

        day_range = (0, 7)
        current_hours = [None, None]
        for identifier in opening_hours_raw[2:]:
            if identifier:
                days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun', 'PH']

                day_list_raw = re.split(r', | and | & ', identifier)
                day_range_list = []

                for day_item_raw in day_list_raw:
                    day_range_raw = day_item_raw.split('-')
                    if len(day_range_raw) > 1:
                        day_range = (days.index(day_range_raw[0]), days.index(day_range_raw[1]))

                    if day_item_raw in days:
                        day_range = (days.index(day_item_raw), days.index(day_item_raw))

                    day_range_list.append(day_range)

                is_summer = True if identifier in ['(', 'Summer'] else \
                    False if identifier in [')', 'Winter'] else is_summer

                if identifier.isdigit() and int(identifier) < 2400:
                    current_hours[current_hours.index(None)] = datetime.datetime.strptime(identifier, '%H%M').time()

                if all(current_hours):
                    day_range = day_range_list.pop(0)
                    for day in range(day_range[0], day_range[1] + 1):
                        (summer_hours if is_summer else hours)[day] = current_hours

                    current_hours = [None, None]

        return OperatingHours(
            *hours, *summer_hours,
            is_24_hr=is_24_hr,
            is_daylight=is_daylight
        )

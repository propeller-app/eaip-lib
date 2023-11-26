from __future__ import annotations

from abc import ABC

import re

import eaip.airspace

class Geog(ABC):
    """
    Represents a geographical Airspace object
    """
    data: re.Match
    airspace: 'eaip.airspace.Airspace'

    def __init__(self, data: re.Match, airspace: eaip.airspace.Airspace):
        self.data = data
        self.airspace = airspace

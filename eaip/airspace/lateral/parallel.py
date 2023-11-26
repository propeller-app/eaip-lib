from eaip.airspace.lateral.line import Line

class Parallel(Line):
    """
    Represents a line of latitude in an Airspace object
    """
    def __repr__(self):
        return f'Parallel(start={self.start}, end={self.end})'

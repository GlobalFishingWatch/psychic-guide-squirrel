"""Unittests for ``fishrast.tools``."""


import datetime

from fishrast import tools


def test_date2str():
    year = 2015
    month = 2
    day = 1
    date = datetime.date(year, month, day)
    assert tools.date2str(date) == '{}-{:02d}-{:02d}'.format(year, month, day)

"""Unittests for ``fishrast.daily``."""


import datetime

from fishrast import daily


def test_vessel_presence_query():
    table = 'dataset.table'
    date = datetime.date.today()

    query = daily.vessel_presence_query(table, date, 0.01)
    print(query)

    assert '{' not in query
    assert '}' not in query
    assert date.strftime('%Y%m%d') in query
    assert table in query

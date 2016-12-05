"""General purpose tools."""


from __future__ import division

import numpy as np

from fishrast.enums import DefaultFields


DATE_FMT = "%Y-%m-%d"


def date2str(date):
    """Convert a date to a ``YYYY-MM-DD`` string.

    Parameters
    ----------
    date : datetime.date
        Convert this object to a string.

    Returns
    -------
    str
    """
    return date.strftime(DATE_FMT)


def result2array(
        stream, field, shape, res, dtype=np.float32,
        lat_bin_field=DefaultFields.lat_bin,
        lon_bin_field=DefaultFields.lon_bin):

    """Convert the results of a BigQuery query to a ``numpy`` array.

    Parameters
    ----------

    Returns
    -------
    """
    
    one_over_res = 1 / res

    out = np.zeros(shape, dtype=dtype)
    
    for row in stream:
        lat = int(row[lat_bin_field])
        lon = int(row[lon_bin_field])
        if lat < 90 * one_over_res and lat > -90 * one_over_res and lon > -180 * one_over_res and lon < 180 * one_over_res:
            lat_index = lat + 90 * one_over_res
            lon_index = lon + 180 * one_over_res
            out[lat_index][lon_index] = row[field]

    return out

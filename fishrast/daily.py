"""Daily fishing rasters."""


from __future__ import division

import datetime

from fishrast import tools
from fishrast.enums import DefaultFields


def vessel_presence_query(
        table, date, res,
        lat_field=DefaultFields.lat, lon_field=DefaultFields.lon,
        lat_bin_field=DefaultFields.lat_bin,
        lon_bin_field=DefaultFields.lon_bin):

    """Produce the query necessary to build a daily vessel presence density.

    Prameters
    ---------
    table : str
        Query this ``dataset.table``.
    date : datetime.date

    res : float

    lat_field : str

    ...
    """

    return """
        SELECT
          INTEGER(FLOOR({lat_field} * {one_over_res})) {lat_bin_field},
          INTEGER(FLOOR({lon_field} * {one_over_res})) {lon_bin_field},
          SUM(IF(last_timestamp IS NOT NULL, (timestamp-last_timestamp)/3600000000,
            (timestamp - TIMESTAMP("{today}"))/3600000000)/2 +
        IF(next_timestamp IS NOT NULL, (next_timestamp - timestamp)/3600000000,
          (TIMESTAMP("{tomorrow}") - timestamp)/3600000000 )/2) hours
        FROM
          [{table}.{date_no_dash}]
        WHERE
          seg_id NOT IN (
          SELECT
            seg_id
          FROM
            [scratch_david_seg_analysis_661b.{year}_segments]
          WHERE
            (point_count<20
              AND terrestrial_positions = point_count)
            OR ((min_lon >= 0 // these are almost definitely noise
                AND max_lon <= 0.109225)
              OR (min_lat >= 0
                AND max_lat <= 0.109225) ))
          AND lat < 90
          AND lat > -90
          AND lon > -180
          AND lon < 180
        GROUP BY
          lat_bin,
          lon_bin
        """.format(
        table=table,
        today=tools.date2str(date),
        tomorrow=date + datetime.timedelta(days=1),
        date_no_dash=tools.date2str(date).replace('-', ''),
        year=date.year,
        lat_field=lat_field,
        lon_field=lon_field,
        one_over_res=1 / res,
        lat_bin_field=lat_bin_field,
        lon_bin_field=lon_bin_field)

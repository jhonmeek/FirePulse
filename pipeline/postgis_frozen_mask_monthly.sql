-- Read-only: mask learned on GA training observations; floor-cell membership.
WITH ga AS (
  SELECT o.*, floor(ST_Y(o.position) * 20)::integer AS lat_i,
         floor(ST_X(o.position) * 20)::integer AS lon_i
  FROM observations_hotspotobservation o
  JOIN observations_region r ON r.code = 'GA' AND ST_Within(o.position, r.geom)
), training_cells AS (
  SELECT lat_i, lon_i,
         count(*) FILTER (WHERE hotspot_type IN (2, 3)) AS type23,
         count(DISTINCT date_trunc('month', acquired_at AT TIME ZONE 'UTC'))
           FILTER (WHERE source = 'viirs-snpp') AS snpp_months
  FROM ga
  WHERE acquired_at >= TIMESTAMPTZ '2012-02-01 00:00:00+00'
    AND acquired_at < TIMESTAMPTZ '2017-01-01 00:00:00+00'
  GROUP BY lat_i, lon_i
), mask AS (
  SELECT lat_i, lon_i FROM training_cells WHERE type23 >= 20 OR snpp_months >= 48
)
SELECT to_char(date_trunc('month',g.acquired_at AT TIME ZONE 'UTC'),'YYYY-MM') AS month,
       g.source, g.satellite, count(*) AS raw_count,
       count(*) FILTER (WHERE g.hotspot_type = 0) AS type0_count,
       count(*) FILTER (WHERE g.hotspot_type = 0 AND m.lat_i IS NULL) AS type0_unmasked_count,
       count(*) FILTER (WHERE g.hotspot_type = 0 AND m.lat_i IS NOT NULL) AS type0_masked_count
FROM ga g LEFT JOIN mask m ON g.lat_i=m.lat_i AND g.lon_i=m.lon_i
GROUP BY 1,2,3 ORDER BY 1,2,3;

-- Lecture seule : mêmes observations importées, avant et après frontière GA.
SELECT to_char(date_trunc('month', o.acquired_at AT TIME ZONE 'UTC'), 'YYYY-MM') AS month,
       o.source, o.satellite,
       count(*) AS country_count,
       count(*) FILTER (WHERE ST_Within(o.position, r.geom)) AS ga_count
FROM observations_hotspotobservation AS o
CROSS JOIN observations_region AS r
WHERE r.code = 'GA'
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

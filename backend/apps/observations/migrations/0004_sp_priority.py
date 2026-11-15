from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("observations", "0003_nrt_counting")]

    operations = [
        migrations.RunSQL(
            sql="""
                WITH ranked AS (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY source, satellite, DATE_TRUNC('minute', acquired_at),
                            ROUND(ST_Y(position)::numeric, 5),
                            ROUND(ST_X(position)::numeric, 5)
                        ORDER BY is_nrt ASC, id ASC
                    ) AS rank,
                    BOOL_OR(is_nrt) OVER (
                        PARTITION BY source, satellite, DATE_TRUNC('minute', acquired_at),
                            ROUND(ST_Y(position)::numeric, 5),
                            ROUND(ST_X(position)::numeric, 5)
                    ) AS has_nrt
                    FROM observations_hotspotobservation
                )
                UPDATE observations_hotspotobservation AS o
                SET counts_in_aggregates = (NOT ranked.has_nrt OR ranked.rank = 1)
                FROM ranked
                WHERE o.id = ranked.id;
            """,
            reverse_sql="""
                WITH ranked AS (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY source, satellite, acquired_at,
                            ROUND(ST_Y(position)::numeric, 5),
                            ROUND(ST_X(position)::numeric, 5)
                        ORDER BY id
                    ) AS rank
                    FROM observations_hotspotobservation
                    WHERE is_nrt
                )
                UPDATE observations_hotspotobservation AS o
                SET counts_in_aggregates = CASE
                    WHEN o.is_nrt THEN ranked.rank = 1 ELSE TRUE END
                FROM ranked
                WHERE o.id = ranked.id;
                UPDATE observations_hotspotobservation
                SET counts_in_aggregates = TRUE WHERE NOT is_nrt;
            """,
        ),
    ]

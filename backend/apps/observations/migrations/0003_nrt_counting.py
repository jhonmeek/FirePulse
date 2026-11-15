from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("observations", "0002_nullable_hotspot_type")]

    operations = [
        migrations.AddField(
            model_name="hotspotobservation",
            name="counts_in_aggregates",
            field=models.BooleanField(default=True, db_index=True),
        ),
        migrations.RunSQL(
            sql="""
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
                SET counts_in_aggregates = FALSE
                FROM ranked
                WHERE o.id = ranked.id AND ranked.rank > 1;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

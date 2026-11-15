from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("observations", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="hotspotobservation",
            name="hotspot_type",
            field=models.PositiveSmallIntegerField(
                null=True,
                blank=True,
                db_index=True,
                help_text="FIRMS type: 0=vegetation fire, 1=volcano, 2=static land, 3=offshore; null=unknown",
            ),
        ),
    ]

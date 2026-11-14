"""Load Gabon country (ADM0) and province (ADM1) boundaries into PostGIS."""

import json
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.core.management.base import BaseCommand, CommandError

from apps.api.cache import invalidate_api_cache
from apps.observations.models import Region, RegionTypeChoices


def _to_multipolygon(geom_dict: dict) -> MultiPolygon:
    geom = GEOSGeometry(json.dumps(geom_dict), srid=4326)
    if isinstance(geom, Polygon):
        return MultiPolygon(geom, srid=4326)
    if isinstance(geom, MultiPolygon):
        return geom
    raise CommandError(f"Unsupported geometry type: {geom.geom_type}")


class Command(BaseCommand):
    """Idempotently load Gabon ADM0 and ADM1 GeoJSON files into Region."""

    help = "Load Gabon country and province GeoJSON boundaries into Region."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--boundaries-dir",
            default="/data/boundaries",
            help="Directory containing gabon_adm0.geojson and gabon_adm1.geojson",
        )

    def handle(self, *args, **options) -> None:
        bdir = Path(options["boundaries_dir"])
        files = [
            (bdir / "gabon_adm0.geojson", RegionTypeChoices.COUNTRY, "GA"),
            (bdir / "gabon_adm1.geojson", RegionTypeChoices.PROVINCE, None),
        ]

        upserted = 0
        for path, region_type, code_override in files:
            if not path.exists():
                raise CommandError(f"Boundary file not found: {path}")
            payload = json.loads(path.read_text(encoding="utf-8"))
            for feat in payload.get("features", []):
                props = feat.get("properties", {})
                code = (code_override or props.get("shapeISO") or props.get("shapeID") or "").strip()
                name = (props.get("shapeName") or code).strip()
                mpoly = _to_multipolygon(feat["geometry"])
                west, south, east, north = mpoly.extent
                Region.objects.update_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "region_type": region_type,
                        "geom": mpoly,
                        "bbox_json": [round(west, 5), round(south, 5), round(east, 5), round(north, 5)],
                        "is_custom_supported": True,
                    },
                )
                upserted += 1

        invalidate_api_cache()
        self.stdout.write(self.style.SUCCESS(f"Loaded/updated {upserted} regions cleanly."))

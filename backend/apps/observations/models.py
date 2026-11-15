"""Spatial and raw satellite hotspot observation models (PostGIS)."""

from django.contrib.gis.db import models as gis_models
from django.db import models


class SourceChoices(models.TextChoices):
    MODIS = "modis", "MODIS (Terra + Aqua)"
    VIIRS_SNPP = "viirs-snpp", "VIIRS Suomi-NPP"
    VIIRS_NOAA20 = "viirs-noaa20", "VIIRS NOAA-20"
    VIIRS_NOAA21 = "viirs-noaa21", "VIIRS NOAA-21"


class ProcessingLevelChoices(models.TextChoices):
    SP = "SP", "Standard Processing"
    NRT = "NRT", "Near Real-Time"


class ConfidenceTierChoices(models.TextChoices):
    LOW = "low", "Low"
    NOMINAL = "nominal", "Nominal"
    HIGH = "high", "High"


class RegionTypeChoices(models.TextChoices):
    COUNTRY = "country", "Country"
    PROVINCE = "province", "Province / Sub-region"
    STUDY_AREA = "study_area", "Study Area"
    CUSTOM = "custom", "Custom"


class Region(models.Model):
    """Geographic region (country or sub-region) used to filter and aggregate hotspots."""

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    region_type = models.CharField(
        max_length=20,
        choices=RegionTypeChoices.choices,
        default=RegionTypeChoices.COUNTRY,
    )
    geom = gis_models.MultiPolygonField(srid=4326, spatial_index=True)
    bbox_json = models.JSONField(default=list, help_text="[west, south, east, north]")
    is_custom_supported = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} ({self.name})"


class ImportBatch(models.Model):
    """Provenance record for each ingested NASA FIRMS file or API pull."""

    source = models.CharField(max_length=20, choices=SourceChoices.choices, db_index=True)
    processing_level = models.CharField(max_length=10, choices=ProcessingLevelChoices.choices)
    product_version = models.CharField(max_length=30, blank=True)
    file_name = models.CharField(max_length=255)
    file_sha256 = models.CharField(max_length=64, unique=True)
    row_count = models.PositiveIntegerField(default=0)
    min_date = models.DateField(null=True, blank=True)
    max_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-imported_at", "file_name"]

    def __str__(self) -> str:
        return f"{self.source} [{self.processing_level}] - {self.file_name}"


class StaticFlareMaskCell(models.Model):
    """0.05 deg persistent thermal cell identifying gas flares or industrial static sites."""

    cell_id = models.CharField(max_length=40, unique=True)
    grid_deg = models.FloatField(default=0.05)
    geom = gis_models.PolygonField(srid=4326, spatial_index=True)
    type23_count = models.PositiveIntegerField(default=0)
    active_months_snpp = models.PositiveSmallIntegerField(default=0)
    reason = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-type23_count", "cell_id"]

    def __str__(self) -> str:
        return f"{self.cell_id} (type2/3={self.type23_count})"


class HotspotObservation(models.Model):
    """Normalized active-fire/thermal-anomaly detection from MODIS or VIIRS."""

    batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        related_name="observations",
    )
    source = models.CharField(max_length=20, choices=SourceChoices.choices, db_index=True)
    satellite = models.CharField(max_length=20, db_index=True)
    instrument = models.CharField(max_length=20)
    acquired_at = models.DateTimeField(db_index=True)
    position = gis_models.PointField(srid=4326, spatial_index=True)
    frp = models.FloatField(null=True, blank=True)
    brightness_mir = models.FloatField(null=True, blank=True)
    brightness_tir = models.FloatField(null=True, blank=True)
    scan = models.FloatField(null=True, blank=True)
    track = models.FloatField(null=True, blank=True)
    confidence_raw = models.CharField(max_length=20)
    confidence_tier = models.CharField(
        max_length=10,
        choices=ConfidenceTierChoices.choices,
        db_index=True,
    )
    daynight = models.CharField(max_length=1, choices=[("D", "Day"), ("N", "Night")])
    hotspot_type = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="FIRMS type: 0=vegetation fire, 1=volcano, 2=static land, 3=offshore; null=unknown",
    )
    is_static_masked = models.BooleanField(default=False, db_index=True)
    product_version = models.CharField(max_length=30)
    is_nrt = models.BooleanField(default=False, db_index=True)
    original_hash = models.CharField(max_length=64, unique=True)

    class Meta:
        indexes = [
            models.Index(fields=["source", "acquired_at"], name="idx_obs_src_acq"),
            models.Index(
                fields=["is_static_masked", "hotspot_type", "acquired_at"],
                name="idx_obs_clean_acq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source}/{self.satellite} @ {self.acquired_at:%Y-%m-%d %H:%M}"


class GridCellMonth(models.Model):
    """Pre-aggregated 0.25 deg monthly sensor counts for fast maps and custom polygon queries."""

    cell_id = models.CharField(max_length=40, db_index=True)
    geom = gis_models.PolygonField(srid=4326, spatial_index=True)
    centroid = gis_models.PointField(srid=4326, spatial_index=True)
    month = models.DateField(db_index=True, help_text="First day of calendar month")
    filter_static = models.BooleanField(default=True, db_index=True)
    modis_count = models.PositiveIntegerField(default=0)
    modis_terra_count = models.PositiveIntegerField(default=0)
    modis_aqua_count = models.PositiveIntegerField(default=0)
    viirs_snpp_count = models.PositiveIntegerField(default=0)
    viirs_noaa20_count = models.PositiveIntegerField(default=0)
    frp_sum_modis = models.FloatField(default=0.0)
    frp_sum_snpp = models.FloatField(default=0.0)
    frp_sum_noaa20 = models.FloatField(default=0.0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cell_id", "month", "filter_static"],
                name="uq_grid_cell_month_filter",
            )
        ]
        indexes = [
            models.Index(fields=["month", "filter_static"], name="idx_grid_month_filter"),
        ]

    def __str__(self) -> str:
        return f"{self.cell_id} [{self.month:%Y-%m}] static={self.filter_static}"

"""Calibration, historical baseline, and harmonized series models."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class SensorRegimeChoices(models.TextChoices):
    PARTIAL_YEAR = "partial_year", "Partial Year (2000-11/12)"
    MODIS_TERRA_ONLY = "modis_terra_only", "MODIS Terra-only Reconstructed"
    MODIS_TERRA_AQUA = "modis_terra_aqua", "MODIS Terra+Aqua Reconstructed"
    VIIRS_SNPP_OBSERVED = "viirs_snpp_observed", "VIIRS S-NPP Observed"
    VIIRS_NOAA20_BRIDGE = "viirs_noaa20_bridge", "VIIRS NOAA-20 Bridge (Post Nov 2026)"
    MISSING = "missing", "No Observation"


class CoverageStatusChoices(models.TextChoices):
    COMPLETE_SP = "complete_sp", "Complete Standard Processing"
    PARTIAL_SP = "partial_sp", "Partial Standard Processing"
    MIXED_SP_NRT = "mixed_sp_nrt", "Mixed SP + NRT"
    NRT_ONLY = "nrt_only", "Near Real-Time Only"
    NO_DATA = "no_data", "No Data"


class CalibrationRun(models.Model):
    """Metadata, learned parameters, and out-of-sample metrics for a calibration run."""

    region = models.ForeignKey(
        "observations.Region",
        on_delete=models.CASCADE,
        related_name="calibration_runs",
        null=True,
        blank=True,
    )
    filter_static = models.BooleanField(default=True)
    method_name = models.CharField(max_length=64, default="power_law_log1p_static_masked")
    method_version = models.CharField(max_length=30, default="v2.0")
    reference_scale = models.CharField(max_length=40, default="VIIRS_375m_SNPP_equiv")
    train_start = models.DateField()
    train_end = models.DateField()
    test_start = models.DateField()
    test_end = models.DateField()
    params_json = models.JSONField(default=dict)
    metrics_json = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        code = self.region.code if self.region else "GLOBAL"
        return f"{code} {self.method_name} ({self.method_version})"


class MonthlyBaseline(models.Model):
    """Per-calendar-month historical median and IQR across reference years."""

    region = models.ForeignKey(
        "observations.Region",
        on_delete=models.CASCADE,
        related_name="monthly_baselines",
    )
    calibration_run = models.ForeignKey(
        CalibrationRun,
        on_delete=models.CASCADE,
        related_name="baselines",
    )
    month_num = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    filter_static = models.BooleanField(default=True)
    baseline_median = models.FloatField()
    iqr_p25 = models.FloatField(null=True, blank=True)
    iqr_p75 = models.FloatField(null=True, blank=True)
    reference_years_count = models.PositiveSmallIntegerField(default=0)
    reference_period = models.CharField(max_length=32, default="2001-2025")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["region", "calibration_run", "month_num", "filter_static"],
                name="uq_monthly_baseline",
            )
        ]
        ordering = ["region", "month_num"]

    def __str__(self) -> str:
        return f"{self.region.code} m={self.month_num:02d} med={self.baseline_median:.1f}"


class HarmonizedMonthSeries(models.Model):
    """Monthly raw + harmonized hotspot activity series with uncertainty and anomalies."""

    region = models.ForeignKey(
        "observations.Region",
        on_delete=models.CASCADE,
        related_name="harmonized_series",
    )
    calibration_run = models.ForeignKey(
        CalibrationRun,
        on_delete=models.CASCADE,
        related_name="series_rows",
    )
    month = models.DateField(db_index=True, help_text="First day of calendar month")
    filter_static = models.BooleanField(default=True, db_index=True)
    modis_count = models.PositiveIntegerField(null=True, blank=True)
    modis_terra_count = models.PositiveIntegerField(null=True, blank=True)
    modis_aqua_count = models.PositiveIntegerField(null=True, blank=True)
    viirs_snpp_count = models.PositiveIntegerField(null=True, blank=True)
    viirs_noaa20_count = models.PositiveIntegerField(null=True, blank=True)
    harmonized_value = models.FloatField(null=True, blank=True)
    ci_low = models.FloatField(null=True, blank=True)
    ci_high = models.FloatField(null=True, blank=True)
    baseline_median = models.FloatField(null=True, blank=True)
    baseline_iqr_p25 = models.FloatField(null=True, blank=True)
    baseline_iqr_p75 = models.FloatField(null=True, blank=True)
    anomaly_percent = models.FloatField(null=True, blank=True)
    anomaly_absolute = models.FloatField(null=True, blank=True)
    sensor_regime = models.CharField(max_length=30, choices=SensorRegimeChoices.choices)
    coverage_status = models.CharField(max_length=20, choices=CoverageStatusChoices.choices)
    method_version = models.CharField(max_length=30, default="v2.0")
    uncertainty_note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["region", "calibration_run", "month", "filter_static"],
                name="uq_harmonized_month",
            )
        ]
        indexes = [
            models.Index(fields=["region", "filter_static", "month"], name="idx_harm_reg_flt_mo"),
        ]
        ordering = ["region", "month"]

    def __str__(self) -> str:
        return f"{self.region.code} {self.month:%Y-%m} ({self.sensor_regime})"

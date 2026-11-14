from django.apps import AppConfig


class ApiConfig(AppConfig):
    """Configuration for the FirePulse REST API v1 app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.api"

    def ready(self) -> None:
        from django.db.models.signals import post_delete, post_save

        from apps.api.cache import invalidate_api_cache
        from apps.harmonization.models import (
            CalibrationRun,
            HarmonizedMonthSeries,
            MonthlyBaseline,
        )
        from apps.observations.models import (
            GridCellMonth,
            HotspotObservation,
            ImportBatch,
            Region,
            StaticFlareMaskCell,
        )

        for model in (
            Region,
            ImportBatch,
            StaticFlareMaskCell,
            HotspotObservation,
            GridCellMonth,
            CalibrationRun,
            MonthlyBaseline,
            HarmonizedMonthSeries,
        ):
            uid_save = f"firepulse_cache_save_{model._meta.label_lower}"
            uid_del = f"firepulse_cache_del_{model._meta.label_lower}"
            post_save.connect(invalidate_api_cache, sender=model, dispatch_uid=uid_save)
            post_delete.connect(invalidate_api_cache, sender=model, dispatch_uid=uid_del)

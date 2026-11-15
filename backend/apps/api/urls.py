"""URL routing for FirePulse REST API v1."""

from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health_view, name="api-health"),
    path("regions/", views.regions_view, name="api-regions"),
    path("coverage/", views.coverage_view, name="api-coverage"),
    path("calendar/", views.calendar_view, name="api-calendar"),
    path("anomalies/", views.anomalies_view, name="api-anomalies"),
    path("hotspots/", views.hotspots_view, name="api-hotspots"),
    path("recent-unknown-detections/", views.recent_unknown_detections_view, name="api-recent-unknown-detections"),
    path("methodology/", views.methodology_view, name="api-methodology"),
    path("export/", views.export_view, name="api-export"),
]

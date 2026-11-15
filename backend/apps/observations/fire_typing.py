"""Contextual type of a FIRMS hotspot: thermal nature + landscape, never the cause.

Two independent NASA sources are combined:

1. FIRMS ``type`` (standard MODIS/VIIRS products): 0 presumed vegetation fire,
   1 active volcano, 2 other static land source, 3 offshore/water. Absent in
   most NRT feeds: kept as ``unavailable``, never replaced by 0.
2. MCD12Q1 C6.1 ``LC_Type1`` (IGBP, 500 m, annual since 2001): land cover at the
   detection location, ideally for the same year.

The result answers "in which landscape was this hotspot detected?". It does not
identify the origin (slash-and-burn, lightning, arson...): ``cause`` is always
``unknown``. A 375 m VIIRS pixel and a 500 m land-cover cell do not overlap
exactly, so a heterogeneous neighbourhood yields ``mixed`` / ``indeterminate``.

Pure Python, no Django or raster dependency: the land-cover raster lookup is
injected by the caller (see ``classify_observation``).
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime

CAUSE_UNKNOWN = "unknown"
METHOD = "firms_type_and_land_cover_overlay"
LAND_COVER_SOURCE = "NASA MCD12Q1 C6.1 LC_Type1 (IGBP)"
LAND_COVER_RESOLUTION_M = 500
# Minimum share of the dominant IGBP class around the detection to name a landscape.
# Heuristic default, not calibrated against ground truth.
DEFAULT_MIXED_THRESHOLD = 0.6

THERMAL_TYPES = {
    0: ("presumed_vegetation_fire", "Feu de végétation présumé"),
    1: ("presumed_volcanic", "Activité volcanique présumée"),
    2: ("other_static_land_source", "Autre source thermique terrestre statique"),
    3: ("offshore_or_water", "Détection offshore ou sur l'eau"),
}

# IGBP code -> (official name, FirePulse landscape)
IGBP_CLASSES = {
    1: ("Evergreen Needleleaf Forests", "forest"),
    2: ("Evergreen Broadleaf Forests", "tropical_forest"),
    3: ("Deciduous Needleleaf Forests", "forest"),
    4: ("Deciduous Broadleaf Forests", "forest"),
    5: ("Mixed Forests", "forest"),
    6: ("Closed Shrublands", "shrubland"),
    7: ("Open Shrublands", "shrubland"),
    8: ("Woody Savannas", "savanna"),
    9: ("Savannas", "savanna"),
    10: ("Grasslands", "grassland"),
    11: ("Permanent Wetlands", "wetland"),
    12: ("Croplands", "cropland"),
    13: ("Urban and Built-up Lands", "urban"),
    14: ("Cropland/Natural Vegetation Mosaics", "cropland_mosaic"),
    15: ("Permanent Snow and Ice", "snow_ice"),
    16: ("Barren", "barren"),
    17: ("Water Bodies", "water"),
}
NO_DATA_CLASSES = {0, 255}  # 255 = unclassified in MCD12Q1
NON_BURNABLE = {"snow_ice", "barren", "water"}

LABELS = {
    "tropical_forest": "Point chaud en forêt tropicale",
    "forest": "Point chaud en milieu forestier",
    "shrubland": "Point chaud en zone arbustive",
    "savanna": "Point chaud en savane",
    "grassland": "Point chaud en prairie",
    "wetland": "Point chaud en zone humide",
    "cropland": "Point chaud en zone cultivée",
    "cropland_mosaic": "Point chaud en mosaïque cultures / végétation naturelle",
    "urban": "Point chaud en zone urbanisée",
    "snow_ice": "Point chaud sur surface non végétalisée (indéterminé)",
    "barren": "Point chaud sur surface non végétalisée (indéterminé)",
    "water": "Point chaud sur pixel d'eau (indéterminé)",
    "mixed": "Point chaud en milieu mixte / indéterminé",
    "unknown": "Point chaud — milieu indisponible",
}
PERSISTENT_UNTYPED_LABEL = "Source thermique persistante — type indéterminé"


@dataclass(frozen=True)
class LandCoverSample:
    """Land-cover value read at a detection location.

    ``dominant_fraction`` is the share (0-1) of ``igbp_class`` in the window
    around the detection (e.g. 3x3 cells); ``None`` if not computed.
    """

    igbp_class: int | None
    year: int | None
    dominant_fraction: float | None = None
    source: str = LAND_COVER_SOURCE
    spatial_resolution_m: int = LAND_COVER_RESOLUTION_M


@dataclass(frozen=True)
class HotspotType:
    thermal_type: str
    thermal_type_status: str  # provided | unavailable
    landscape: str
    status: str  # inferred | indeterminate | unavailable | not_applicable
    label: str
    land_cover: dict | None
    in_persistent_cell: bool | None
    flags: tuple[str, ...] = field(default_factory=tuple)
    method: str = METHOD
    cause: str = CAUSE_UNKNOWN

    def to_dict(self) -> dict:
        return {
            "thermal_type": self.thermal_type,
            "thermal_type_status": self.thermal_type_status,
            "land_cover": self.land_cover,
            "in_persistent_cell": self.in_persistent_cell,
            "classification": {
                "landscape": self.landscape,
                "label": self.label,
                "method": self.method,
                "status": self.status,
                "cause": self.cause,
                "flags": list(self.flags),
            },
        }


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _land_cover_payload(sample: LandCoverSample, detection_year: int | None) -> dict:
    name, category = IGBP_CLASSES.get(sample.igbp_class, (None, "unknown"))
    offset = None
    if sample.year is not None and detection_year is not None:
        offset = sample.year - detection_year
    return {
        "category": category,
        "igbp_class": sample.igbp_class,
        "igbp_name": name,
        "source": sample.source,
        "year": sample.year,
        "year_offset": offset,
        "spatial_resolution_m": sample.spatial_resolution_m,
        "dominant_fraction": sample.dominant_fraction,
    }


def _validate(firms_type, land_cover: LandCoverSample | None, mixed_threshold: float) -> None:
    if firms_type is not None and (not _is_int(firms_type) or firms_type not in THERMAL_TYPES):
        raise ValueError(f"invalid FIRMS type: {firms_type!r}")
    if not 0 <= mixed_threshold <= 1:
        raise ValueError("mixed_threshold must be within [0, 1]")
    if land_cover is None:
        return
    igbp = land_cover.igbp_class
    if igbp is not None and (not _is_int(igbp) or (igbp not in IGBP_CLASSES and igbp not in NO_DATA_CLASSES)):
        raise ValueError(f"invalid IGBP class: {igbp!r}")
    fraction = land_cover.dominant_fraction
    if fraction is not None and not (math.isfinite(fraction) and 0 <= fraction <= 1):
        raise ValueError(f"invalid dominant_fraction: {fraction!r}")


def classify_hotspot(
    firms_type: int | None,
    land_cover: LandCoverSample | None,
    *,
    detection_year: int | None = None,
    in_persistent_cell: bool | None = None,
    mixed_threshold: float = DEFAULT_MIXED_THRESHOLD,
) -> HotspotType:
    """Determine the contextual type of one hotspot.

    Rules, in order:
    1. FIRMS type 1/2/3 -> non-vegetation thermal source, landscape not applicable.
    2. No usable land cover -> landscape ``unknown``, status ``unavailable``.
    3. Type absent and detection inside a persistent thermal cell -> ``indeterminate``
       (likely static industrial source, cannot be asserted).
    4. Dominant class share below ``mixed_threshold`` -> ``mixed`` / ``indeterminate``.
    5. Presumed vegetation fire over snow/barren/water -> ``indeterminate``.
    6. Otherwise -> IGBP landscape, status ``inferred``.
    ``in_persistent_cell`` is reported as a separate flag, never merged into types.
    """
    _validate(firms_type, land_cover, mixed_threshold)
    flags: list[str] = []
    if firms_type is None:
        thermal, thermal_status = "unavailable", "unavailable"
        flags.append("thermal_type_unavailable")
    else:
        thermal, thermal_status = THERMAL_TYPES[firms_type][0], "provided"
    if in_persistent_cell:
        flags.append("persistent_thermal_cell")

    lc_payload = _land_cover_payload(land_cover, detection_year) if land_cover else None
    if lc_payload and lc_payload["year_offset"] not in (None, 0):
        flags.append("land_cover_year_mismatch")

    def build(landscape: str, status: str, label: str) -> HotspotType:
        return HotspotType(thermal, thermal_status, landscape, status, label, lc_payload, in_persistent_cell, tuple(flags))

    if firms_type in (1, 2, 3):
        return build("not_applicable", "not_applicable", THERMAL_TYPES[firms_type][1])
    if lc_payload is None or lc_payload["category"] == "unknown":
        return build("unknown", "unavailable", LABELS["unknown"])
    category = lc_payload["category"]
    if firms_type is None and in_persistent_cell:
        return build(category, "indeterminate", PERSISTENT_UNTYPED_LABEL)
    fraction = land_cover.dominant_fraction
    if fraction is not None and fraction < mixed_threshold:
        flags.append("heterogeneous_land_cover")
        return build("mixed", "indeterminate", LABELS["mixed"])
    if category in NON_BURNABLE:
        flags.append("land_cover_inconsistent_with_thermal_type")
        return build(category, "indeterminate", LABELS[category])
    return build(category, "inferred", LABELS[category])


def select_land_cover_year(detection_year: int, available_years: Iterable[int]) -> int | None:
    """Same year if available, else the closest earlier year, else the closest later one."""
    years = sorted(set(available_years))
    if not years:
        return None
    if detection_year in years:
        return detection_year
    earlier = [y for y in years if y < detection_year]
    return earlier[-1] if earlier else years[0]


def _year_of(value) -> int:
    if isinstance(value, (datetime, date)):
        return value.year
    return int(str(value)[:4])


LandCoverLookup = Callable[[float, float, int], "LandCoverSample | None"]


def classify_observation(
    observation: Mapping,
    lookup: LandCoverLookup,
    *,
    mixed_threshold: float = DEFAULT_MIXED_THRESHOLD,
) -> dict:
    """Classify a normalized/NRT observation dict.

    Reads ``latitude``, ``longitude``, ``acquired_at`` and ``type_nasa`` (NRT
    artefacts) or ``hotspot_type`` (historical rows); ``in_persistent_cell`` is
    optional. ``lookup(lat, lon, year)`` returns the land-cover sample.
    """
    lat, lon = float(observation["latitude"]), float(observation["longitude"])
    year = _year_of(observation["acquired_at"])
    firms_type = observation["type_nasa"] if "type_nasa" in observation else observation.get("hotspot_type")
    result = classify_hotspot(
        firms_type,
        lookup(lat, lon, year),
        detection_year=year,
        in_persistent_cell=observation.get("in_persistent_cell"),
        mixed_threshold=mixed_threshold,
    )
    return result.to_dict()

from django.contrib.gis import admin

from .models import (
    GridCellMonth,
    HotspotObservation,
    ImportBatch,
    Region,
    StaticFlareMaskCell,
)

admin.site.register(Region, admin.GISModelAdmin)
admin.site.register(ImportBatch)
admin.site.register(StaticFlareMaskCell, admin.GISModelAdmin)
admin.site.register(HotspotObservation, admin.GISModelAdmin)
admin.site.register(GridCellMonth, admin.GISModelAdmin)

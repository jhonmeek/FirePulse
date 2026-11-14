from django.contrib import admin

from .models import CalibrationRun, HarmonizedMonthSeries, MonthlyBaseline

admin.site.register(CalibrationRun)
admin.site.register(MonthlyBaseline)
admin.site.register(HarmonizedMonthSeries)

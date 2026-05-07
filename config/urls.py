from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('apps.api.urls')),
    path('sales/', include('apps.sales.urls')),
    path('purchases/', include('apps.purchases.urls')),
    path('inventory/', include('apps.inventory.urls')),
    path('treasury/', include('apps.treasury.urls')),
    path('expenses/', include('apps.expenses.urls')),
    path('reports/', include('apps.reports.urls')),
    path('hr/', include('apps.hr.urls')),
    path('assets/', include('apps.assets.urls')),
    path('accounts/', include('allauth.urls')),
    path('access/', include('apps.users.urls')),
    path('', include('apps.core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

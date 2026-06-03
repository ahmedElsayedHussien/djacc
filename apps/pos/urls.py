from django.urls import path
from . import views

app_name = 'pos'

urlpatterns = [
    path('', views.pos_dashboard, name='dashboard'),
    path('session/open/', views.open_session, name='session-open'),
    path('session/close/', views.close_session, name='session-close'),
    path('checkout/', views.checkout, name='checkout'),
    path('stations/', views.station_list, name='station-list'),
    path('stations/create/', views.station_create, name='station-create'),
    path('stations/<int:pk>/update/', views.station_update, name='station-update'),
    path('stations/<int:pk>/delete/', views.station_delete, name='station-delete'),
    path('sessions/', views.session_list, name='session-list'),
    path('orders/<int:pk>/cancel/', views.cancel_order, name='order-cancel'),
    path('orders/<int:pk>/return/', views.return_order_items, name='order-return'),
    path('sessions/<int:pk>/collect-shortage/', views.collect_shortage, name='collect-shortage'),
]

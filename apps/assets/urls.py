from django.urls import path
from . import views

app_name = 'assets'

urlpatterns = [
    path('', views.AssetDashboardView.as_view(), name='dashboard'),
    path('list/', views.AssetListView.as_view(), name='asset-list'),
    path('create/', views.AssetCreateView.as_view(), name='asset-create'),
    path('categories/', views.AssetCategoryListView.as_view(), name='category-list'),
    path('categories/create/', views.AssetCategoryCreateView.as_view(), name='category-create'),
    path('run-depreciation/', views.RunDepreciationView.as_view(), name='run-depreciation'),
    path('dispose/<int:pk>/', views.AssetDisposeView.as_view(), name='asset-dispose'),

]

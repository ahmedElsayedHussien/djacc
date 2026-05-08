from django.urls import path
from . import views

app_name = 'expenses'

urlpatterns = [
    path('categories/', views.ExpenseCategoryListView.as_view(), name='category-list'),
    path('categories/create/', views.ExpenseCategoryCreateView.as_view(), name='category-create'),

    path('custody/', views.CustodyListView.as_view(), name='custody-list'),
    path('custody/create/', views.CustodyCreateView.as_view(), name='custody-create'),
    path('custody/<int:pk>/', views.CustodyDetailView.as_view(), name='custody-detail'),
    path('custody/<int:custody_pk>/settle/', views.CustodySettlementCreateView.as_view(), name='custody-settle'),

    path('', views.ExpenseDashboardView.as_view(), name='dashboard'),
    path('list/', views.ExpenseListView.as_view(), name='expense-list'),
    path('create/', views.ExpenseCreateView.as_view(), name='expense-create'),
    path('<int:pk>/', views.ExpenseDetailView.as_view(), name='expense-detail'),
    path('<int:pk>/post/', views.ExpensePostView.as_view(), name='expense-post'),
    path('<int:pk>/reverse/', views.ExpenseReverseView.as_view(), name='expense-reverse'),
    path('<int:pk>/approve/', views.ExpenseApproveView.as_view(), name='expense-approve'),
]

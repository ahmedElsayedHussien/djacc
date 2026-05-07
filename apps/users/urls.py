from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # Role (Group) Management
    path('roles/', views.RoleListView.as_view(), name='role-list'),
    path('roles/create/', views.RoleCreateView.as_view(), name='role-create'),
    path('roles/<int:pk>/edit/', views.RoleUpdateView.as_view(), name='role-edit'),
    path('roles/<int:pk>/delete/', views.RoleDeleteView.as_view(), name='role-delete'),

    # User Role Management
    path('users/', views.UserListView.as_view(), name='user-list'),
    path('users/<int:pk>/roles/', views.UserRoleUpdateView.as_view(), name='user-roles-edit'),
]

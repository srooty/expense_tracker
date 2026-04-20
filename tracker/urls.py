from django.urls import path
from . import views

urlpatterns = [
    path('', views.groups_list, name='groups_list'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('groups/', views.groups_list, name='groups_list'),
    path('groups/create/', views.group_create, name='group_create'),
    path('groups/<int:group_id>/', views.group_dashboard, name='group_dashboard'),
    path('groups/<int:group_id>/expenses/add/', views.expense_create, name='expense_create'),
    path('groups/<int:group_id>/expenses/<int:expense_id>/edit/', views.expense_edit, name='expense_edit'),
    path('groups/<int:group_id>/expenses/<int:expense_id>/delete/', views.expense_delete, name='expense_delete'),
    path('groups/<int:group_id>/settle/', views.settle_create, name='settle_create'),
    path('groups/<int:group_id>/leave/', views.leave_group, name='leave_group'),
]
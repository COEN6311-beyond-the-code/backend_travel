from django.urls import path
from user import views

urlpatterns = [
    path('register/', views.register, name='register'), # user registers
    path('register_handle/', views.register_handle, name='register_handle'), # handle user registers
    path('user_login/', views.user_login, name='user_login'), # user login
]
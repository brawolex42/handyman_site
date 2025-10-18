# core/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),

    path('services/', views.services, name='services'),
    path('service/<int:pk>/', views.service_detail, name='service_detail'),

    path('booking/', views.booking_create, name='booking'),
    path('booking/<int:pk>/cancel/', views.booking_cancel, name='booking_cancel'),
    path('booking/<int:pk>/pdf/', views.booking_pdf, name='booking_pdf'),
    path('thanks/', views.thanks, name='thanks'),

    path('reviews/', views.reviews, name='reviews'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Регистрация/логин
    path('register/', views.register_view, name='register'),
    path('login/',  auth_views.LoginView.as_view(template_name='auth_login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),

    # Подтверждение e-mail и повторная отправка письма
    path('activate/<uidb64>/<token>/', views.activate_account, name='activate'),
    path('resend-activation/', views.resend_activation, name='resend_activation'),

    # Owner
    path('owner/', views.owner_dashboard, name='owner_dashboard'),
    path('owner/booking/<int:pk>/', views.owner_booking_detail, name='owner_booking_detail'),
    path('owner/booking/<int:pk>/done/', views.owner_booking_done, name='owner_booking_done'),
    path('owner/booking/<int:pk>/set-hours/', views.owner_booking_set_hours, name='owner_booking_set_hours'),
    path('owner/booking/<int:pk>/delete/', views.owner_booking_delete, name='owner_booking_delete'),

    path('owner/booking/<int:pk>/archive/', views.owner_booking_archive, name='owner_booking_archive'),
    path('owner/booking/<int:pk>/restore/', views.owner_booking_restore, name='owner_booking_restore'),

    path('owner/booking/<int:pk>/cash/', views.owner_booking_cash_pay, name='owner_booking_cash_pay'),

    path('owner/export.csv', views.owner_export_bookings_csv, name='export_bookings_csv'),
    path('owner/stats/', views.owner_stats, name='owner_stats'),

    # Payments (SumUp)
    path('api/payments/sumup/charge/', views.sumup_charge, name='sumup_charge'),
    path('api/payments/sumup/webhook/', views.sumup_webhook, name='sumup_webhook'),
]

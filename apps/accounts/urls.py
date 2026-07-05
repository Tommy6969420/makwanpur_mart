from django.urls import path
from . import views

app_name = "accounts"
urlpatterns = [
    path("login/", views.login, name="login"),
    path("register/", views.register, name="register"),
    path("verify-otp/", views.verify_otp, name="verify_otp"),
    path("profile/", views.profile, name="profile"),
    path("profile/edit/", views.profile_edit, name="profile_edit"),
    path("change-password/", views.change_password, name="change_password"),
    path("password-reset/", views.password_reset, name="password_reset"),
    path("password-reset/confirm/", views.password_reset_confirm, name="password_reset_confirm"),
    path("addresses/", views.address_list, name="address_list"),
    path("addresses/form/", views.address_form, name="address_form"),
    path("vendor/register/", views.vendor_register, name="vendor_register"),
    path("vendor/agreement/", views.vendor_agreement, name="vendor_agreement"),
    path("vendor/status/", views.vendor_status, name="vendor_status"),
    path("vendor/dashboard/", views.vendor_dashboard, name="vendor_dashboard"),
    path("vendor/profile/edit/", views.vendor_profile_edit, name="vendor_profile_edit"),
    path("rider/register/", views.rider_register, name="rider_register"),
    path("rider/dashboard/", views.rider_dashboard, name="rider_dashboard"),
    path("rider/profile/edit/", views.rider_profile_edit, name="rider_profile_edit"),
]

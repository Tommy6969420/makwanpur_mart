from django.shortcuts import render


def login(request):
    return render(request, "accounts/login.html")


def register(request):
    return render(request, "accounts/register.html")


def verify_otp(request):
    return render(request, "accounts/verify_otp.html")


def profile(request):
    return render(request, "accounts/profile.html")


def profile_edit(request):
    return render(request, "accounts/profile_edit.html")


def change_password(request):
    return render(request, "accounts/change_password.html")


def password_reset(request):
    return render(request, "accounts/password_reset.html")


def password_reset_confirm(request):
    return render(request, "accounts/password_reset_confirm.html")


def address_list(request):
    return render(request, "accounts/address_list.html")


def address_form(request):
    return render(request, "accounts/address_form.html")


def vendor_register(request):
    return render(request, "accounts/vendor_register.html")


def vendor_agreement(request):
    return render(request, "accounts/vendor_agreement.html")


def vendor_status(request):
    return render(request, "accounts/vendor_status.html")


def vendor_dashboard(request):
    return render(request, "accounts/vendor_dashboard.html")


def vendor_profile_edit(request):
    return render(request, "accounts/vendor_profile_edit.html")


def rider_register(request):
    return render(request, "accounts/rider_register.html")


def rider_dashboard(request):
    return render(request, "accounts/rider_dashboard.html")


def rider_profile_edit(request):
    return render(request, "accounts/rider_profile_edit.html")
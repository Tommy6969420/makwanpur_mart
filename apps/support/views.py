from django.shortcuts import render


def help_center(request):
    return render(request, "support/help_center.html")


def complaint_form(request):
    return render(request, "support/complaint_form.html")


def complaint_list(request):
    return render(request, "support/complaint_list.html")


def complaint_detail(request, complaint_id):
    return render(request, "support/complaint_detail.html", {"complaint_id": complaint_id})

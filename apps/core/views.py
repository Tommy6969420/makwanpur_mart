from django.shortcuts import render


def home(request):
    return render(request, "core/home.html")


def about(request):
    return render(request, "core/about.html")


def contact(request):
    return render(request, "core/contact.html")


def return_policy(request):
    return render(request, "core/return_policy.html")


def privacy(request):
    return render(request, "core/privacy.html")


def terms(request):
    return render(request, "core/terms.html")


def faq(request):
    return render(request, "core/faq.html")


def search_results(request):
    return render(request, "core/search_results.html")
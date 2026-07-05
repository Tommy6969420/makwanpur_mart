from django.urls import path
from . import views

app_name = "core"
urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("return-policy/", views.return_policy, name="return_policy"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("faq/", views.faq, name="faq"),
    path("search/", views.search_results, name="search_results"),
]

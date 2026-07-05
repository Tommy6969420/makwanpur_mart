from django.urls import path
from . import views

app_name = "support"
urlpatterns = [
    path("help-center/", views.help_center, name="help_center"),
    path("complaints/", views.complaint_form, name="complaint_form"),
    path("complaints/list/", views.complaint_list, name="complaint_list"),
    path("complaints/<int:complaint_id>/", views.complaint_detail, name="complaint_detail"),
]
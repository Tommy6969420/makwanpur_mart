from django.urls import path
from . import views

app_name = "delivery"
urlpatterns = [
    path("deliveries/<int:delivery_id>/", views.delivery_detail, name="delivery_detail"),
    path("rider-deliveries/", views.rider_delivery_list, name="rider_delivery_list"),
]

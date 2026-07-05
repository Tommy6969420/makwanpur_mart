from django.urls import path
from . import views

app_name = "orders"
urlpatterns = [
    path("cart/", views.cart, name="cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("confirmation/", views.order_confirmation, name="order_confirmation"),
    path("orders/", views.order_list, name="order_list"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
    path("orders/cancel/", views.order_cancel, name="order_cancel"),
    path("payment-failed/", views.payment_failed, name="payment_failed"),
    path("payment-redirect/", views.payment_redirect, name="payment_redirect"),
    path("returns/<int:order_id>/", views.return_request, name="return_request"),
    path("vendor/orders/", views.vendor_order_list, name="vendor_order_list"),
    path("vendor/orders/<int:order_id>/", views.vendor_order_detail, name="vendor_order_detail"),
    path("vendor/earnings/", views.vendor_earnings, name="vendor_earnings"),
]
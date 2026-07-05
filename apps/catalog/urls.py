from django.urls import path
from . import views

app_name = "catalog"
urlpatterns = [
    path("categories/", views.category_list, name="category_list"),
    path("categories/<slug:slug>/", views.category_detail, name="category_detail"),
    path("products/", views.product_list, name="product_list"),
    path("products/<slug:slug>/", views.product_detail, name="product_detail"),
    path("reviews/form/", views.review_form, name="review_form"),
    path("vendor/products/", views.vendor_product_list, name="vendor_product_list"),
    path("vendor/products/form/", views.vendor_product_form, name="vendor_product_form"),
    path("vendor/<slug:slug>/", views.vendor_storefront, name="vendor_storefront"),
    path("wishlist/", views.wishlist, name="wishlist"),
]

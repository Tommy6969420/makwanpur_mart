from django.shortcuts import render


def cart(request):
    return render(request, "orders/cart.html")


def checkout(request):
    return render(request, "orders/checkout.html")


def order_confirmation(request):
    return render(request, "orders/order_confirmation.html")


def order_list(request):
    return render(request, "orders/order_list.html")


def order_detail(request, order_id):
    return render(request, "orders/order_detail.html", {"order_id": order_id})


def order_cancel(request):
    return render(request, "orders/order_cancel.html")


def payment_failed(request):
    return render(request, "orders/payment_failed.html")


def payment_redirect(request):
    return render(request, "orders/payment_redirect.html")


def return_request(request, order_id):
    return render(request, "orders/return_request.html", {"order_id": order_id})


def vendor_order_list(request):
    return render(request, "orders/vendor_order_list.html")


def vendor_order_detail(request, order_id):
    return render(request, "orders/vendor_order_detail.html", {"order_id": order_id})


def vendor_earnings(request):
    return render(request, "orders/vendor_earnings.html")

from django.shortcuts import render


def delivery_detail(request, delivery_id):
    return render(request, "delivery/delivery_detail.html", {"delivery_id": delivery_id})


def rider_delivery_list(request):
    return render(request, "delivery/rider_delivery_list.html")

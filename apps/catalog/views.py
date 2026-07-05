from django.shortcuts import render


def category_list(request):
    return render(request, "catalog/category_list.html")


def category_detail(request, slug):
    return render(request, "catalog/category_detail.html", {"slug": slug})


def product_list(request):
    return render(request, "catalog/product_list.html")


def product_detail(request, slug):
    return render(request, "catalog/product_detail.html", {"slug": slug})


def review_form(request):
    return render(request, "catalog/review_form.html")


def vendor_product_list(request):
    return render(request, "catalog/vendor_product_list.html")


def vendor_product_form(request):
    return render(request, "catalog/vendor_product_form.html")


def vendor_storefront(request, slug):
    return render(request, "catalog/vendor_storefront.html", {"slug": slug})


def wishlist(request):
    return render(request, "catalog/wishlist.html")

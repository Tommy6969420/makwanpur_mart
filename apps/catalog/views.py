"""
Views for catalog app.
Handles categories, products, reviews, wishlist, and vendor operations.
"""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q, F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import DetailView, ListView, TemplateView, View

from .forms import CategoryForm, ProductForm, ProductImageForm, ProductSearchForm, ProductVariantForm, ReviewForm
from .models import Category, Product, ProductImage, ProductVariant, Review, Wishlist
from .services import (
    add_to_wishlist, available_stock, check_product_available, create_product,
    get_category_breadcrumb, get_category_product_count, get_categories_hierarchy,
    get_featured_products, get_new_arrivals, get_product_reviews, get_product_with_details,
    get_products_by_category, get_review_stats, get_user_wishlist, is_in_wishlist,
    remove_from_wishlist, search_products, submit_review, toggle_wishlist, update_product_stock
)
from apps.accounts.models import User


# =============================================================================
# Category Views
# =============================================================================

class CategoryListView(ListView):
    """List all categories."""
    
    model = Category
    template_name = 'catalog/category_list.html'
    context_object_name = 'categories'
    
    def get_queryset(self):
        return Category.objects.filter(
            is_active=True,
            parent__isnull=True
        ).prefetch_related('children', 'children__children')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add product counts
        for category in context['categories']:
            category.product_count = get_category_product_count(category)
        
        return context


class CategoryDetailView(View):
    """Display products in a category."""
    
    template_name = 'catalog/category_detail.html'
    
    def get(self, request, slug):
        category = get_object_or_404(Category, slug=slug, is_active=True)
        
        # Get products
        products = get_products_by_category(category)
        
        # Pagination
        page = request.GET.get('page', 1)
        paginator = Paginator(products, 12)
        try:
            products_page = paginator.page(page)
        except (PageNotAnInteger, EmptyPage):
            products_page = paginator.page(1)
        
        context = {
            'category': category,
            'categories': Category.objects.filter(is_active=True, parent=category),
            'products': products_page,
            'breadcrumb': get_category_breadcrumb(category),
            'product_count': products.count(),
        }
        
        return render(request, self.template_name, context)


# =============================================================================
# Product Views
# =============================================================================

class ProductListView(ListView):
    """List all products with filtering and sorting."""
    
    model = Product
    template_name = 'catalog/product_list.html'
    context_object_name = 'products'
    paginate_by = 12
    
    def get_queryset(self):
        products = Product.objects.filter(is_active=True).select_related(
            'vendor', 'category', 'category__parent'
        ).prefetch_related('images')
        
        # Apply filters
        category_slug = self.request.GET.get('category')
        if category_slug:
            category = get_object_or_404(Category, slug=category_slug)
            category_ids = [category.id]
            for child in category.children.all():
                category_ids.append(child.id)
            products = products.filter(category_id__in=category_ids)
        
        # Sorting
        sort = self.request.GET.get('sort', 'newest')
        sort_options = {
            'newest': '-created_at',
            'price_low': 'effective_price',
            'price_high': '-effective_price',
        }
        products = products.order_by(sort_options.get(sort, '-created_at'))
        
        return products
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.filter(is_active=True, parent__isnull=True).prefetch_related('children')
        context['current_sort'] = self.request.GET.get('sort', 'newest')
        
        # Get category filter if any
        category_slug = self.request.GET.get('category')
        if category_slug:
            context['active_category'] = get_object_or_404(Category, slug=category_slug)
        
        return context


class ProductDetailView(View):
    """Display product details."""
    
    template_name = 'catalog/product_detail.html'
    
    def get(self, request, slug):
        try:
            product = Product.objects.select_related(
                'vendor', 'vendor__user', 'category', 'category__parent'
            ).prefetch_related('images', 'variants', 'reviews').get(slug=slug, is_active=True)
        except Product.DoesNotExist:
            return render(request, 'errors/404.html', {'message': 'Product not found'}, status=404)
        
        details = get_product_with_details(product.id)
        
        # Get reviews
        reviews_data = get_product_reviews(product)
        
        # Check wishlist status
        in_wishlist = False
        if request.user.is_authenticated:
            in_wishlist = is_in_wishlist(request.user, product)
        
        context = {
            'product': product,
            'details': details,
            'reviews': reviews_data['reviews'][:5],  # Show first 5 reviews
            'review_stats': get_review_stats(product),
            'in_wishlist': in_wishlist,
            'primary_image': product.images.filter(is_primary=True).first() or product.images.first(),
        }
        
        return render(request, self.template_name, context)


# =============================================================================
# HTMX Search Views
# =============================================================================

def product_search(request):
    """HTMX product search with filters."""
    query = request.GET.get('q', '')
    category_id = request.GET.get('category')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    sort = request.GET.get('sort', 'newest')
    page = int(request.GET.get('page', 1))
    
    category = None
    if category_id:
        category = get_object_or_404(Category, id=category_id)
    
    results = search_products(
        query=query,
        category=category,
        min_price=float(min_price) if min_price else None,
        max_price=float(max_price) if max_price else None,
        sort_by=sort,
        page=page,
        per_page=12
    )
    
    # Check if HTMX request
    if request.headers.get('HX-Request'):
        return render(request, 'catalog/partials/product_grid.html', {
            'products': results['results'],
            'page': results['page'],
            'total_pages': results['total_pages'],
        })
    
    return render(request, 'core/search_results.html', {
        'results': results['results'],
        'total_count': results['total_count'],
        'query': query,
        'categories': Category.objects.filter(is_active=True),
    })


@require_http_methods(["GET"])
def search_suggestions(request):
    """Return search suggestions as user types."""
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse({'suggestions': []})
    
    products = Product.objects.filter(
        is_active=True,
        name__icontains=query
    ).values_list('name', flat=True)[:5]
    
    categories = Category.objects.filter(
        is_active=True,
        name__icontains=query
    ).values_list('name', flat=True)[:3]
    
    suggestions = list(products) + list(categories)
    
    return JsonResponse({'suggestions': suggestions[:8]})


# =============================================================================
# Review Views
# =============================================================================

class ReviewFormView(LoginRequiredMixin, View):
    """Submit a product review."""
    
    template_name = 'catalog/review_form.html'
    
    def get(self, request, product_slug):
        product = get_object_or_404(Product, slug=product_slug, is_active=True)
        
        # Check if user has purchased this product
        # For demo purposes, we'll allow review if user is authenticated
        form = ReviewForm()
        return render(request, self.template_name, {'form': form, 'product': product})
    
    def post(self, request, product_slug):
        product = get_object_or_404(Product, slug=product_slug, is_active=True)
        form = ReviewForm(data=request.POST)
        
        if form.is_valid():
            rating = form.cleaned_data['rating']
            comment = form.cleaned_data['comment']
            
            # For demo, we'll create a review without order_item
            # In production, validate against actual orders
            review = Review.objects.create(
                product=product,
                order_item=None,  # Would be validated in production
                rating=rating,
                comment=comment
            )
            
            messages.success(request, 'Review submitted! Thank you.')
            
            if request.headers.get('HX-Request'):
                return render(request, 'catalog/partials/review_success.html', {'review': review})
            
            return redirect('catalog:product_detail', slug=product_slug)
        
        return render(request, self.template_name, {'form': form, 'product': product})


# =============================================================================
# Wishlist Views
# =============================================================================

class WishlistView(LoginRequiredMixin, ListView):
    """Display user's wishlist."""
    
    model = Wishlist
    template_name = 'catalog/wishlist.html'
    context_object_name = 'wishlist_items'
    
    def get_queryset(self):
        return Wishlist.objects.filter(user=self.request.user).select_related(
            'product', 'product__vendor', 'product__category'
        ).prefetch_related('product__images')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['product_count'] = context['wishlist_items'].count()
        return context


@require_POST
@login_required
def toggle_wishlist_ajax(request):
    """Toggle product wishlist status via HTMX/AJAX."""
    product_id = request.POST.get('product_id')
    product = get_object_or_404(Product, id=product_id, is_active=True)
    
    added = toggle_wishlist(request.user, product)
    
    if request.headers.get('HX-Request'):
        context = {
            'in_wishlist': added,
            'product': product,
            'wishlist_count': request.user.wishlist_items.count()
        }
        return render(request, 'catalog/partials/wishlist_button.html', context)
    
    return JsonResponse({
        'success': True,
        'added': added,
        'wishlist_count': request.user.wishlist_items.count()
    })


# =============================================================================
# Vendor Product Management Views
# =============================================================================

class VendorProductListView(LoginRequiredMixin, View):
    """List vendor's own products."""
    
    template_name = 'catalog/vendor_product_list.html'
    
    def get(self, request):
        if not hasattr(request.user, 'vendor_profile'):
            raise PermissionDenied("You are not a vendor.")
        
        vendor = request.user.vendor_profile
        products = Product.objects.filter(vendor=vendor).select_related(
            'category'
        ).prefetch_related('images').order_by('-created_at')
        
        return render(request, self.template_name, {
            'products': products,
            'vendor': vendor,
        })


class VendorProductFormView(LoginRequiredMixin, View):
    """Create or edit a product."""
    
    template_name = 'catalog/vendor_product_form.html'
    
    def get(self, request, product_id=None):
        if not hasattr(request.user, 'vendor_profile'):
            raise PermissionDenied("You are not a vendor.")
        
        product = None
        if product_id:
            product = get_object_or_404(Product, id=product_id, vendor=request.user.vendor_profile)
        
        form = ProductForm(instance=product)
        return render(request, self.template_name, {'form': form, 'product': product})
    
    def post(self, request, product_id=None):
        if not hasattr(request.user, 'vendor_profile'):
            raise PermissionDenied("You are not a vendor.")
        
        product = None
        if product_id:
            product = get_object_or_404(Product, id=product_id, vendor=request.user.vendor_profile)
        
        form = ProductForm(data=request.POST, instance=product)
        if form.is_valid():
            product = form.save(commit=False)
            product.vendor = request.user.vendor_profile
            
            # Generate slug if new product
            if not product.slug:
                from django.utils.text import slugify
                base_slug = slugify(f"{request.user.vendor_profile.shop_slug}-{product.name}")
                slug = base_slug
                counter = 1
                while Product.objects.filter(slug=slug).exclude(pk=product.pk if product.pk else 0).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                product.slug = slug
            
            product.save()
            
            messages.success(request, f'Product {"updated" if product_id else "created"} successfully!')
            
            if request.headers.get('HX-Request'):
                return render(request, 'catalog/partials/product_save_success.html', {'product': product})
            
            return redirect('catalog:vendor_product_list')
        
        return render(request, self.template_name, {'form': form, 'product': product})


class VendorProductDeleteView(LoginRequiredMixin, View):
    """Delete a product (soft delete - just deactivate)."""
    
    def post(self, request, product_id):
        if not hasattr(request.user, 'vendor_profile'):
            raise PermissionDenied("You are not a vendor.")
        
        product = get_object_or_404(Product, id=product_id, vendor=request.user.vendor_profile)
        product.is_active = False
        product.save(update_fields=['is_active'])
        
        messages.success(request, 'Product deleted.')
        
        if request.headers.get('HX-Request'):
            return render(request, 'catalog/partials/product_deleted.html')
        
        return redirect('catalog:vendor_product_list')


# =============================================================================
# Vendor Storefront (Public View)
# =============================================================================

class VendorStorefrontView(View):
    """Public vendor storefront."""
    
    template_name = 'catalog/vendor_storefront.html'
    
    def get(self, request, slug):
        from apps.accounts.models import VendorProfile
        
        vendor = get_object_or_404(VendorProfile, shop_slug=slug)
        
        if not vendor.is_verified:
            # Could show a "pending verification" page instead
            pass
        
        products = Product.objects.filter(
            vendor=vendor,
            is_active=True
        ).select_related('category').prefetch_related('images').order_by('-created_at')
        
        # Stats
        stats = {
            'total_products': products.count(),
            'average_rating': vendor.average_rating,
            'total_sales': vendor.total_sales,
        }
        
        return render(request, self.template_name, {
            'vendor': vendor,
            'products': products,
            'stats': stats,
        })


# =============================================================================
# HTMX Partial Views
# =============================================================================

def product_quick_view(request, product_id):
    """Return quick view modal for product."""
    product = get_object_or_404(Product, id=product_id, is_active=True)
    details = get_product_with_details(product.id)
    
    in_wishlist = False
    if request.user.is_authenticated:
        in_wishlist = is_in_wishlist(request.user, product)
    
    context = {
        'product': product,
        'details': details,
        'in_wishlist': in_wishlist,
    }
    
    return render(request, 'catalog/partials/quick_view.html', context)


def product_variants_partial(request, product_id):
    """Return variants for a product (for variant selection)."""
    product = get_object_or_404(Product, id=product_id, is_active=True)
    variants = product.variants.all()
    
    return render(request, 'catalog/partials/variant_selector.html', {
        'product': product,
        'variants': variants,
    })


def category_children_partial(request, category_id):
    """Return child categories for a category."""
    category = get_object_or_404(Category, id=category_id)
    children = category.children.filter(is_active=True)
    
    return render(request, 'catalog/partials/category_children.html', {
        'category': category,
        'children': children,
    })
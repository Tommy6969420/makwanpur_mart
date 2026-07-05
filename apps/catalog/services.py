"""
Services for catalog app.
Business logic for products, categories, reviews, wishlist, and search.
"""
from django.db.models import Avg, Count, F, Q, Sum
from django.utils import timezone

from .models import Category, Product, ProductImage, ProductVariant, Review, Wishlist


# =============================================================================
# Product Services
# =============================================================================

def get_active_products():
    """Get all active products."""
    return Product.objects.filter(is_active=True)


def get_product_by_slug(slug: str) -> Product:
    """Get product by slug."""
    return Product.objects.get(slug=slug, is_active=True)


def get_products_by_category(category: Category, include_subcategories: bool = True) -> list:
    """
    Get products in a category.
    If include_subcategories is True, also include products from child categories.
    """
    if include_subcategories:
        category_ids = [category.id]
        for child in category.children.all():
            category_ids.append(child.id)
            # Get grandchildren
            category_ids.extend(child.children.values_list('id', flat=True))
        
        return Product.objects.filter(
            category_id__in=category_ids,
            is_active=True
        ).select_related('vendor', 'category')
    
    return Product.objects.filter(
        category=category,
        is_active=True
    ).select_related('vendor', 'category')


def get_product_with_details(product_id: int) -> dict:
    """Get comprehensive product details."""
    product = Product.objects.select_related(
        'vendor', 'vendor__user', 'category', 'category__parent'
    ).prefetch_related('images', 'variants', 'reviews').get(id=product_id, is_active=True)
    
    # Get review stats
    review_stats = Review.objects.filter(product=product).aggregate(
        avg_rating=Avg('rating'),
        total_reviews=Count('id')
    )
    
    # Calculate total stock (considering variants)
    if product.has_variants:
        total_stock = product.variants.aggregate(total=Sum('stock_quantity'))['total'] or 0
    else:
        total_stock = product.stock_quantity
    
    return {
        'product': product,
        'review_stats': review_stats,
        'total_stock': total_stock,
        'is_available': total_stock > 0,
    }


def available_stock(product: Product, variant: ProductVariant = None) -> int:
    """
    Get available stock for a product (optionally specific variant).
    """
    if variant:
        return variant.stock_quantity
    
    if product.has_variants:
        return product.variants.aggregate(total=Sum('stock_quantity'))['total'] or 0
    
    return product.stock_quantity


def check_product_available(product: Product, quantity: int = 1, variant: ProductVariant = None) -> bool:
    """Check if requested quantity is available."""
    return available_stock(product, variant) >= quantity


# =============================================================================
# Category Services
# =============================================================================

def get_categories_hierarchy():
    """Get category hierarchy for navigation."""
    return Category.objects.filter(
        is_active=True,
        parent__isnull=True
    ).prefetch_related('children', 'children__children')


def get_category_breadcrumb(category: Category) -> list:
    """Get breadcrumb path for a category."""
    path = []
    current = category
    while current:
        path.insert(0, current)
        current = current.parent
    return path


def get_category_product_count(category: Category, include_subcategories: bool = True) -> int:
    """Get total product count for a category."""
    if include_subcategories:
        category_ids = [category.id]
        for child in category.children.all():
            category_ids.append(child.id)
            category_ids.extend(child.children.values_list('id', flat=True))
        
        return Product.objects.filter(category_id__in=category_ids, is_active=True).count()
    
    return Product.objects.filter(category=category, is_active=True).count()


# =============================================================================
# Search Services
# =============================================================================

def search_products(query: str, category: Category = None, 
                    min_price: float = None, max_price: float = None,
                    condition: str = None, sort_by: str = 'newest',
                    page: int = 1, per_page: int = 12) -> dict:
    """
    Search products with filters.
    Returns dict with results and pagination info.
    """
    # Base queryset
    products = Product.objects.filter(is_active=True)
    
    # Text search
    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(sku__icontains=query)
        )
    
    # Category filter
    if category:
        category_ids = [category.id]
        for child in category.children.all():
            category_ids.append(child.id)
        products = products.filter(category_id__in=category_ids)
    
    # Price filters
    if min_price is not None:
        products = products.filter(Q(discounted_price__gte=min_price) | 
                                   Q(discounted_price__isnull=True, price__gte=min_price))
    if max_price is not None:
        products = products.filter(Q(discounted_price__lte=max_price) | 
                                   Q(discounted_price__isnull=True, price__lte=max_price))
    
    # Condition filter
    if condition:
        products = products.filter(condition=condition)
    
    # Sorting
    sort_options = {
        'newest': '-created_at',
        'price_low': 'effective_price',
        'price_high': '-effective_price',
        'rating': '-vendor__average_rating',
    }
    products = products.order_by(sort_options.get(sort_by, '-created_at'))
    
    # Add vendor rating annotation
    products = products.select_related('vendor', 'category', 'category__parent')
    
    # Pagination
    total_count = products.count()
    start = (page - 1) * per_page
    end = start + per_page
    results = list(products[start:end])
    
    return {
        'results': results,
        'total_count': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': (total_count + per_page - 1) // per_page,
    }


# =============================================================================
# Wishlist Services
# =============================================================================

def add_to_wishlist(user, product: Product) -> Wishlist:
    """Add product to user's wishlist."""
    wishlist_item, created = Wishlist.objects.get_or_create(
        user=user,
        product=product
    )
    return wishlist_item, created


def remove_from_wishlist(user, product: Product) -> bool:
    """Remove product from user's wishlist."""
    deleted, _ = Wishlist.objects.filter(user=user, product=product).delete()
    return deleted > 0


def toggle_wishlist(user, product: Product) -> bool:
    """
    Toggle wishlist status.
    Returns True if added, False if removed.
    """
    try:
        item = Wishlist.objects.get(user=user, product=product)
        item.delete()
        return False  # Removed
    except Wishlist.DoesNotExist:
        Wishlist.objects.create(user=user, product=product)
        return True  # Added


def get_user_wishlist(user) -> list:
    """Get user's wishlist items with product details."""
    return Wishlist.objects.filter(user=user).select_related(
        'product', 'product__vendor', 'product__category', 'product__images'
    ).order_by('-added_at')


def is_in_wishlist(user, product: Product) -> bool:
    """Check if product is in user's wishlist."""
    return Wishlist.objects.filter(user=user, product=product).exists()


# =============================================================================
# Review Services
# =============================================================================

def submit_review(user, product: Product, order_item, rating: int, comment: str = '') -> Review:
    """Submit a product review."""
    review = Review.objects.create(
        product=product,
        order_item=order_item,
        rating=rating,
        comment=comment
    )
    
    # Update vendor stats asynchronously (in production, use Celery)
    from apps.accounts.services import refresh_vendor_stats
    refresh_vendor_stats(product.vendor)
    
    return review


def get_product_reviews(product: Product, page: int = 1, per_page: int = 10) -> dict:
    """Get paginated reviews for a product."""
    reviews = Review.objects.filter(product=product).select_related(
        'order_item', 'order_item__order', 'order_item__order__customer'
    ).order_by('-created_at')
    
    total_count = reviews.count()
    start = (page - 1) * per_page
    end = start + per_page
    
    return {
        'reviews': list(reviews[start:end]),
        'total_count': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': (total_count + per_page - 1) // per_page,
    }


def get_review_stats(product: Product) -> dict:
    """Get review statistics for a product."""
    stats = Review.objects.filter(product=product).aggregate(
        avg_rating=Avg('rating'),
        total_reviews=Count('id'),
        rating_1=Count('id', filter=Q(rating=1)),
        rating_2=Count('id', filter=Q(rating=2)),
        rating_3=Count('id', filter=Q(rating=3)),
        rating_4=Count('id', filter=Q(rating=4)),
        rating_5=Count('id', filter=Q(rating=5)),
    )
    
    return stats


def vendor_respond_to_review(review: Review, response: str) -> Review:
    """Add vendor response to a review."""
    review.vendor_response = response
    review.save(update_fields=['vendor_response'])
    return review


# =============================================================================
# Vendor Product Management
# =============================================================================

def get_vendor_products(vendor, include_inactive: bool = False) -> list:
    """Get all products for a vendor."""
    queryset = Product.objects.filter(vendor=vendor)
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset.select_related('category').prefetch_related('images', 'variants').order_by('-created_at')


def create_product(vendor, data: dict) -> Product:
    """Create a new product for a vendor."""
    from django.db.models import F
    
    category = data.get('category')
    
    product = Product.objects.create(
        vendor=vendor,
        name=data['name'],
        category=category,
        description=data.get('description', ''),
        price=data['price'],
        discounted_price=data.get('discounted_price'),
        stock_quantity=data.get('stock_quantity', 0),
        sku=data.get('sku', ''),
        condition=data.get('condition', Product.Condition.NEW),
        is_active=data.get('is_active', True),
        slug=data.get('slug', f"{vendor.shop_slug}-{data['name'].lower().replace(' ', '-')}")
    )
    
    return product


def update_product_stock(product: Product, quantity_change: int, variant: ProductVariant = None) -> bool:
    """
    Update product stock (decrease for orders, increase for restocks).
    Returns True if successful.
    """
    if variant:
        variant.stock_quantity = max(0, variant.stock_quantity + quantity_change)
        variant.save(update_fields=['stock_quantity'])
    else:
        product.stock_quantity = max(0, product.stock_quantity + quantity_change)
        product.save(update_fields=['stock_quantity'])
    
    return True


# =============================================================================
# Featured Products
# =============================================================================

def get_featured_products(limit: int = 8) -> list:
    """Get featured products for homepage."""
    return Product.objects.filter(
        is_active=True,
        vendor__verification_status='verified'
    ).select_related('vendor', 'category').prefetch_related(
        'images'
    ).order_by('-vendor__average_rating', '-created_at')[:limit]


def get_new_arrivals(limit: int = 12) -> list:
    """Get newest products."""
    return Product.objects.filter(
        is_active=True
    ).select_related('vendor', 'category').prefetch_related(
        'images'
    ).order_by('-created_at')[:limit]


def get_best_sellers(limit: int = 8) -> list:
    """Get best selling products."""
    return Product.objects.filter(
        is_active=True,
        vendor__total_sales__gt=0
    ).select_related('vendor', 'category').prefetch_related(
        'images'
    ).order_by('-vendor__total_sales')[:limit]
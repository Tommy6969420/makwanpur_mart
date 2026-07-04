"""
Catalog domain: Category, Product, ProductVariant, ProductImage, Review, Wishlist.

Full-scale build — all spec models live. Review is linked to OrderItem
(verified purchases only), Wishlist is unique per (user, product).
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Category(models.Model):
    """Hierarchical categories (parent self-FK supports 'Clothing > Men's')."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    icon = models.ImageField(upload_to="category_icons/", blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "categories"
        indexes = [models.Index(fields=["is_active"])]

    def __str__(self):
        return f"{self.parent} > {self.name}" if self.parent else self.name


class Product(models.Model):
    """A vendor's listing.

    Stock rules: if the product has variants, per-variant ``stock_quantity``
    is authoritative and this field is ignored (enforced in
    ``apps.catalog.services.available_stock``). Vendors pause listings with
    ``is_active`` instead of deleting (order history keeps its FK).
    """

    class Condition(models.TextChoices):
        NEW = "new", "New"
        USED = "used", "Used"

    vendor = models.ForeignKey("accounts.VendorProfile", on_delete=models.CASCADE, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discounted_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=64, blank=True)
    condition = models.CharField(max_length=5, choices=Condition.choices, default=Condition.NEW)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["vendor", "is_active"]),
            models.Index(fields=["-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["vendor", "slug"], name="unique_slug_per_vendor"),
            models.CheckConstraint(
                condition=models.Q(discounted_price__isnull=True) | models.Q(discounted_price__lt=models.F("price")),
                name="discount_below_price",
            ),
        ]

    @property
    def effective_price(self):
        return self.discounted_price if self.discounted_price is not None else self.price

    @property
    def has_variants(self):
        return self.variants.exists()

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    """Size/colour variant. ``stock_quantity`` overrides the parent product's;
    ``price_override`` (nullable) replaces the parent's effective price."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    size = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=30, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "size", "color"], name="unique_variant_per_product"),
        ]

    @property
    def effective_price(self):
        return self.price_override if self.price_override is not None else self.product.effective_price

    def __str__(self):
        bits = [b for b in (self.size, self.color) if b]
        return f"{self.product.name} ({', '.join(bits) or 'default'})"


class ProductImage(models.Model):
    """Compressed/resized server-side on upload — never trust vendor uploads."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/%Y/%m/")
    is_primary = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"], condition=models.Q(is_primary=True), name="one_primary_image_per_product"
            )
        ]


class Review(models.Model):
    """Verified-purchase review — linked to an OrderItem, not just any user.

    One review per order item (OneToOne). ``vendor_response`` lets the vendor
    reply publicly. On save, a Celery task refreshes
    ``VendorProfile.average_rating`` (denormalized).
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    order_item = models.OneToOneField("orders.OrderItem", on_delete=models.CASCADE, related_name="review")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    vendor_response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["product", "-created_at"])]

    def __str__(self):
        return f"{self.rating}★ on {self.product}"


class Wishlist(models.Model):
    """Saved products, unique per (user, product)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="unique_wishlist_entry")]

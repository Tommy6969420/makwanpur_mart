"""
Accounts domain: User, Address, VendorProfile, RiderProfile.

Full-scale build — all fields from the system-design spec are live
(P1 + P2 + P3). See docs/CHANGES.md for what was un-gated and why.
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


class User(AbstractUser):
    """Custom user — email login, Nepali phone number, role-based access.

    ``email`` is the USERNAME_FIELD (primary login + notification channel).
    ``phone_number`` is unique and OTP-verified at signup — in Nepal phone
    is often more reliable than email and is the delivery contact.
    ``is_active`` doubles as the soft-ban switch (never delete accounts).
    """

    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        VENDOR = "vendor", "Vendor"
        RIDER = "rider", "Rider"
        ADMIN = "admin", "Admin"

    class Language(models.TextChoices):
        ENGLISH = "en", "English"
        NEPALI = "ne", "नेपाली"

    email = models.EmailField(unique=True)
    phone_number = models.CharField(
        max_length=15,
        unique=True,
        validators=[RegexValidator(r"^\+?977?9\d{9}$", "Enter a valid Nepali mobile number.")],
        help_text="Used for SMS notifications and OTP.",
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER)
    is_phone_verified = models.BooleanField(default=False)
    profile_picture = models.ImageField(upload_to="profiles/", blank=True)
    preferred_language = models.CharField(max_length=2, choices=Language.choices, default=Language.ENGLISH)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "phone_number"]

    class Meta:
        indexes = [models.Index(fields=["role", "is_active"])]

    def __str__(self):
        return f"{self.email} ({self.role})"


class Address(models.Model):
    """Delivery address — landmark-first, ward-based (no formal street addressing).

    ``latitude``/``longitude`` feed map-based delivery-zone logic; nullable
    because most addresses are entered without coordinates.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=50, help_text='e.g. "Home", "Shop"')
    full_address = models.TextField()
    landmark = models.TextField(blank=True, help_text="Nearby landmark — often more useful than street address.")
    ward_number = models.PositiveSmallIntegerField()
    is_default = models.BooleanField(default=False)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        verbose_name_plural = "addresses"
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=models.Q(is_default=True), name="one_default_address_per_user"
            )
        ]

    def __str__(self):
        return f"{self.label} — ward {self.ward_number} ({self.user})"


class VendorProfile(models.Model):
    """Vendor shop profile, verification state, and commercial terms.

    INVARIANT: ``commission_rate`` is the *live* rate. It is snapshotted onto
    ``OrderItem.commission_amount`` at order time and never re-read for
    historical orders — changing this rate must never rewrite past payouts.

    ``average_rating`` / ``total_sales`` are denormalized caches maintained by
    ``apps.accounts.services.refresh_vendor_stats`` (called from a Celery task
    on review creation / order delivery) — never computed per page load.
    """

    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    class PayoutMethod(models.TextChoices):
        ESEWA = "esewa", "eSewa"
        KHALTI = "khalti", "Khalti"
        BANK = "bank", "Bank transfer"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vendor_profile")
    shop_name = models.CharField(max_length=120)
    shop_slug = models.SlugField(max_length=140, unique=True)
    shop_description = models.TextField(blank=True)
    shop_logo = models.ImageField(upload_to="shop_logos/", blank=True)
    category = models.ForeignKey(
        "catalog.Category", on_delete=models.PROTECT, related_name="vendors",
        help_text="Primary category the vendor sells in.",
    )
    verification_status = models.CharField(
        max_length=10, choices=VerificationStatus.choices, default=VerificationStatus.PENDING,
        help_text="Set to 'verified' after manual vetting.",
    )
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.00,
        help_text="Per-vendor rate (%). Snapshotted onto OrderItem at order time.",
    )
    agreement_signed_at = models.DateTimeField(null=True, blank=True)
    listing_fee_exempt_until = models.DateField(
        null=True, blank=True, help_text='Implements the "free first year" policy.'
    )
    payout_method = models.CharField(max_length=10, choices=PayoutMethod.choices)
    # SECURITY: swap to EncryptedTextField (django-encrypted-model-fields) before
    # storing real account numbers. Kept as TextField so the scaffold runs without
    # a FIELD_ENCRYPTION_KEY; the swap is a one-line change + migration.
    payout_account_details = models.TextField(help_text="ENCRYPT AT REST in production.")
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    total_sales = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["verification_status"])]

    @property
    def is_verified(self):
        return self.verification_status == self.VerificationStatus.VERIFIED

    def __str__(self):
        return self.shop_name


class RiderProfile(models.Model):
    """Delivery rider — availability toggled by the rider from their panel.

    ``total_deliveries`` is denormalized, incremented in
    ``apps.delivery.services.complete_delivery`` inside the same transaction
    that marks the Delivery delivered.
    """

    class VehicleType(models.TextChoices):
        BIKE = "bike", "Bike"
        BICYCLE = "bicycle", "Bicycle"
        ON_FOOT = "on_foot", "On foot"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rider_profile")
    vehicle_type = models.CharField(max_length=10, choices=VehicleType.choices)
    is_available = models.BooleanField(default=False)
    current_zone = models.ForeignKey(
        "delivery.DeliveryZone", null=True, blank=True, on_delete=models.SET_NULL, related_name="riders"
    )
    total_deliveries = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["is_available"])]

    def __str__(self):
        return f"Rider {self.user.username} ({self.vehicle_type})"

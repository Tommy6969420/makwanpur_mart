"""
Admin configuration for accounts app.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Address, RiderProfile, User, VendorProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for User model."""
    
    list_display = ('email', 'username', 'role', 'is_phone_verified', 'is_active', 'date_joined')
    list_filter = ('role', 'is_active', 'is_phone_verified', 'preferred_language')
    search_fields = ('email', 'username', 'phone_number')
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Personal Info', {'fields': ('phone_number', 'profile_picture', 'preferred_language')}),
        ('Role & Status', {'fields': ('role', 'is_phone_verified', 'is_active')}),
        ('Permissions', {'fields': ('is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'phone_number', 'password1', 'password2', 'role'),
        }),
    )
    
    readonly_fields = ('date_joined', 'last_login')


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    """Admin for Address model."""
    
    list_display = ('label', 'user', 'municipality', 'ward_number', 'is_default')
    list_filter = ('municipality', 'is_default')
    search_fields = ('user__email', 'label', 'full_address', 'landmark')
    raw_id_fields = ('user',)


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    """Admin for VendorProfile model."""
    
    list_display = ('shop_name', 'user', 'category', 'verification_status', 'average_rating', 'total_sales')
    list_filter = ('verification_status', 'category', 'payout_method')
    search_fields = ('shop_name', 'shop_slug', 'user__email')
    raw_id_fields = ('user', 'category')
    readonly_fields = ('average_rating', 'total_sales', 'agreement_signed_at')


@admin.register(RiderProfile)
class RiderProfileAdmin(admin.ModelAdmin):
    """Admin for RiderProfile model."""
    
    list_display = ('__str__', 'user', 'vehicle_type', 'is_available', 'current_zone', 'total_deliveries')
    list_filter = ('vehicle_type', 'is_available', 'current_zone')
    search_fields = ('user__email', 'user__username')
    raw_id_fields = ('user', 'current_zone')
    readonly_fields = ('total_deliveries',)
"""
Admin configuration for support app.
"""
from django.contrib import admin

from .models import AuditLog, GrievanceComplaint, Notification


@admin.register(GrievanceComplaint)
class GrievanceComplaintAdmin(admin.ModelAdmin):
    """Admin for GrievanceComplaint model."""
    
    list_display = ('id', 'order', 'raised_by', 'category', 'status', 'created_at', 'resolved_at')
    list_filter = ('status', 'category')
    search_fields = ('order__order_number', 'raised_by__email', 'description')
    raw_id_fields = ('order', 'raised_by')
    readonly_fields = ('created_at', 'resolved_at')
    
    fieldsets = (
        (None, {'fields': ('order', 'raised_by', 'category', 'status')}),
        ('Details', {'fields': ('description', 'resolution_notes')}),
        ('Timestamps', {'fields': ('created_at', 'resolved_at')}),
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin for Notification model."""
    
    list_display = ('user', 'type', 'title', 'is_read', 'sent_via', 'created_at')
    list_filter = ('type', 'sent_via', 'is_read')
    search_fields = ('user__email', 'title', 'message')
    raw_id_fields = ('user',)
    readonly_fields = ('created_at',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin for AuditLog model (read-only)."""
    
    list_display = ('timestamp', 'user', 'action', 'model_affected', 'object_id', 'ip_address')
    list_filter = ('model_affected', 'action')
    search_fields = ('user__email', 'action', 'object_id')
    readonly_fields = ('user', 'action', 'model_affected', 'object_id', 'timestamp', 'ip_address')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
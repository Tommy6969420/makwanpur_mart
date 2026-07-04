"""
Trust, support & compliance: GrievanceComplaint, Notification, AuditLog.

GrievanceComplaint is legally required under Nepal's E-Commerce Act.
AuditLog records sensitive admin actions (who changed a commission rate,
who resolved a complaint, when) — written via apps.support.services.audit().
"""
from django.conf import settings
from django.db import models


class GrievanceComplaint(models.Model):
    """Legal compliance — Nepal E-Commerce Act grievance handling."""

    class Category(models.TextChoices):
        PRODUCT_ISSUE = "product_issue", "Product issue"
        DELIVERY_ISSUE = "delivery_issue", "Delivery issue"
        PAYMENT_ISSUE = "payment_issue", "Payment issue"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_REVIEW = "in_review", "In review"
        RESOLVED = "resolved", "Resolved"
        ESCALATED = "escalated", "Escalated"

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="complaints")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "-created_at"])]


class Notification(models.Model):
    """User notification, delivered via SMS / push / in-app.

    SMS sending is offloaded to Celery (apps.support.tasks.send_sms_task) —
    user-facing requests never block on Sparrow SMS.
    """

    class Type(models.TextChoices):
        ORDER_UPDATE = "order_update", "Order update"
        PROMO = "promo", "Promotion"
        SYSTEM = "system", "System"

    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        PUSH = "push", "Push"
        IN_APP = "in_app", "In-app"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=15, choices=Type.choices)
    title = models.CharField(max_length=120)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    sent_via = models.CharField(max_length=10, choices=Channel.choices, default=Channel.SMS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read"])]


class AuditLog(models.Model):
    """Immutable record of sensitive actions. ``user`` NULL = system action.
    Write-only by convention: no update/delete views, admin is read-only."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)
    model_affected = models.CharField(max_length=100)
    object_id = models.CharField(max_length=40)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["model_affected", "object_id"])]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.user or 'system'}: {self.action}"

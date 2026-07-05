"""
Views for support app.
Handles help center, complaints, notifications, and admin complaint queue.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import DetailView, ListView, TemplateView, View

from .forms import ComplaintResolutionForm, GrievanceComplaintForm
from .models import AuditLog, GrievanceComplaint, Notification
from .services import (
    create_complaint, get_faq_categories, get_model_audit_trail, 
    get_pending_complaints, get_unread_notification_count, get_user_complaints,
    get_user_notifications, mark_all_notifications_read, mark_notification_read,
    update_complaint_status
)
from apps.accounts.models import User
from apps.orders.models import Order


# =============================================================================
# Help Center
# =============================================================================

class HelpCenterView(TemplateView):
    """Help center with FAQs."""
    
    template_name = 'support/help_center.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['faq_categories'] = get_faq_categories()
        return context


# =============================================================================
# Complaint Views
# =============================================================================

class ComplaintFormView(LoginRequiredMixin, View):
    """Create a new complaint/grievance."""
    
    template_name = 'support/complaint_form.html'
    
    def get(self, request, order_id=None):
        order = None
        if order_id:
            order = get_object_or_404(Order, id=order_id, customer=request.user)
        
        form = GrievanceComplaintForm()
        return render(request, self.template_name, {'form': form, 'order': order})
    
    def post(self, request, order_id=None):
        order = None
        if order_id:
            order = get_object_or_404(Order, id=order_id, customer=request.user)
        else:
            # Get most recent order
            order = Order.objects.filter(customer=request.user).first()
        
        if not order:
            messages.error(request, 'No order found to file complaint for.')
            return redirect('support:help_center')
        
        form = GrievanceComplaintForm(data=request.POST)
        if form.is_valid():
            complaint = create_complaint(
                order=order,
                user=request.user,
                category=form.cleaned_data['category'],
                description=form.cleaned_data['description']
            )
            
            messages.success(request, f'Complaint #{complaint.id} filed successfully! We will review it shortly.')
            
            if request.headers.get('HX-Request'):
                return render(request, 'support/partials/complaint_success.html', {'complaint': complaint})
            
            return redirect('support:complaint_detail', complaint_id=complaint.id)
        
        return render(request, self.template_name, {'form': form, 'order': order})


class ComplaintListView(LoginRequiredMixin, ListView):
    """List user's complaints."""
    
    model = GrievanceComplaint
    template_name = 'support/complaint_list.html'
    context_object_name = 'complaints'
    paginate_by = 10
    
    def get_queryset(self):
        return get_user_complaints(self.request.user)


class ComplaintDetailView(LoginRequiredMixin, View):
    """View complaint details."""
    
    template_name = 'support/complaint_detail.html'
    
    def get(self, request, complaint_id):
        complaint = get_object_or_404(GrievanceComplaint, id=complaint_id, raised_by=request.user)
        
        context = {
            'complaint': complaint,
            'audit_trail': get_model_audit_trail('GrievanceComplaint', complaint.id),
        }
        
        return render(request, self.template_name, context)


# =============================================================================
# Admin Complaint Views
# =============================================================================

class AdminComplaintQueueView(LoginRequiredMixin, TemplateView):
    """Admin view of all complaints."""
    
    template_name = 'support/admin_complaint_queue.html'
    
    def get(self, request):
        if not request.user.is_staff and request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Admin access required.")
        
        status_filter = request.GET.get('status', 'all')
        
        complaints = GrievanceComplaint.objects.select_related(
            'order', 'raised_by'
        ).order_by('-created_at')
        
        if status_filter != 'all':
            complaints = complaints.filter(status=status_filter)
        
        # Pagination
        page = request.GET.get('page', 1)
        paginator = Paginator(complaints, 20)
        try:
            complaints_page = paginator.page(page)
        except (PageNotAnInteger, EmptyPage):
            complaints_page = paginator.page(1)
        
        context = {
            'complaints': complaints_page,
            'status_filter': status_filter,
            'status_counts': {
                'all': GrievanceComplaint.objects.count(),
                'open': GrievanceComplaint.objects.filter(status='open').count(),
                'in_review': GrievanceComplaint.objects.filter(status='in_review').count(),
                'resolved': GrievanceComplaint.objects.filter(status='resolved').count(),
                'escalated': GrievanceComplaint.objects.filter(status='escalated').count(),
            }
        }
        
        return render(request, self.template_name, context)


@login_required
def resolve_complaint_ajax(request, complaint_id):
    """Resolve a complaint (admin)."""
    if not request.user.is_staff and request.user.role != User.Role.ADMIN:
        raise PermissionDenied("Admin access required.")
    
    complaint = get_object_or_404(GrievanceComplaint, id=complaint_id)
    
    if request.method == 'POST':
        form = ComplaintResolutionForm(data=request.POST, instance=complaint)
        if form.is_valid():
            update_complaint_status(
                complaint=complaint,
                new_status=form.cleaned_data['status'],
                notes=form.cleaned_data['resolution_notes'],
                updated_by=request.user
            )
            
            messages.success(request, f'Complaint #{complaint.id} updated successfully.')
            
            if request.headers.get('HX-Request'):
                return render(request, 'support/partials/complaint_resolved.html', {'complaint': complaint})
            
            return redirect('support:admin_complaint_queue')
        
        return render(request, 'support/partials/complaint_resolution_form.html', {
            'complaint': complaint,
            'form': form
        })
    
    form = ComplaintResolutionForm(instance=complaint)
    return render(request, 'support/partials/complaint_resolution_form.html', {
        'complaint': complaint,
        'form': form
    })


# =============================================================================
# Notification Views
# =============================================================================

class NotificationListView(LoginRequiredMixin, ListView):
    """List user notifications."""
    
    model = Notification
    template_name = 'support/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 20
    
    def get_queryset(self):
        return get_user_notifications(self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unread_count'] = get_unread_notification_count(self.request.user)
        return context


@require_POST
@login_required
def mark_notification_read_ajax(request):
    """Mark a notification as read via HTMX."""
    notification_id = request.POST.get('notification_id')
    
    if mark_notification_read(int(notification_id), request.user):
        if request.headers.get('HX-Request'):
            count = get_unread_notification_count(request.user)
            return render(request, 'support/partials/notification_badge.html', {'unread_count': count})
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False, 'error': 'Notification not found'})


@require_POST
@login_required
def mark_all_notifications_read_ajax(request):
    """Mark all notifications as read via HTMX."""
    count = mark_all_notifications_read(request.user)
    
    if request.headers.get('HX-Request'):
        notifications = get_user_notifications(request.user)[:10]
        return render(request, 'support/partials/notification_list.html', {
            'notifications': notifications,
            'unread_count': 0
        })
    
    return JsonResponse({'success': True, 'count': count})
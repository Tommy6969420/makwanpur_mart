"""
Views for accounts app.
Handles user authentication, profile management, addresses, vendor and rider functionality.
"""
import random
import re
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView, View

from .forms import (
    AddressForm, ChangePasswordForm, CustomPasswordResetForm, CustomSetPasswordForm,
    LoginForm, RiderProfileEditForm, RiderRegistrationForm, UserProfileForm,
    UserRegistrationForm, VendorProfileEditForm, VendorRegistrationForm
)
from .models import Address, RiderProfile, User, VendorProfile
from .services import (
    generate_otp, send_otp_sms, verify_otp_code,
    refresh_vendor_stats, refresh_rider_stats
)


# =============================================================================
# Authentication Views
# =============================================================================

class LoginView(View):
    """Handle user login with email authentication."""
    
    template_name = 'accounts/login.html'
    
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('core:home')
        form = LoginForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = LoginForm(data=request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            
            # Authenticate with email
            user = authenticate(request, username=email, password=password)
            
            if user is not None:
                if user.is_active:
                    login(request, user)
                    
                    # Get next URL from GET parameters
                    next_url = request.GET.get('next', reverse('core:home'))
                    return redirect(next_url)
                else:
                    messages.error(request, 'Your account has been deactivated. Please contact support.')
            else:
                messages.error(request, 'Invalid email or password. Please try again.')
        
        return render(request, self.template_name, {'form': form})


class RegisterView(View):
    """Handle new user registration."""
    
    template_name = 'accounts/register.html'
    
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('core:home')
        form = UserRegistrationForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = UserRegistrationForm(data=request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = User.Role.CUSTOMER
            user.save()
            
            # Generate and send OTP
            otp = generate_otp(user)
            # Uncomment in production with SMS gateway configured
            # send_otp_sms(user.phone_number, otp)
            
            # Store user ID in session for OTP verification
            request.session['pending_user_id'] = user.id
            
            messages.success(request, f'Account created! OTP sent to {user.phone_number}')
            return redirect('accounts:verify_otp')
        
        return render(request, self.template_name, {'form': form})


class VerifyOTPView(View):
    """Verify phone number with OTP code."""
    
    template_name = 'accounts/verify_otp.html'
    
    def get(self, request):
        pending_user_id = request.session.get('pending_user_id')
        if not pending_user_id:
            return redirect('accounts:register')
        
        user = get_object_or_404(User, id=pending_user_id)
        context = {
            'phone_number': user.phone_number,
            'masked_phone': f"****{user.phone_number[-7:]}",
            'attempts_remaining': max(0, 3 - (user.otp_attempts or 0)),
        }
        return render(request, self.template_name, context)
    
    def post(self, request):
        pending_user_id = request.session.get('pending_user_id')
        if not pending_user_id:
            return redirect('accounts:register')
        
        user = get_object_or_404(User, id=pending_user_id)
        otp_code = request.POST.get('otp', '').strip()
        
        if verify_otp_code(user, otp_code):
            user.is_phone_verified = True
            user.save(update_fields=['is_phone_verified'])
            
            # Clear session
            del request.session['pending_user_id']
            if 'otp_expiry' in request.session:
                del request.session['otp_expiry']
            
            messages.success(request, 'Phone verified successfully!')
            login(request, user)
            return redirect('core:home')
        else:
            messages.error(request, 'Invalid OTP. Please try again.')
            context = {
                'phone_number': user.phone_number,
                'attempts_remaining': max(0, 3 - (user.otp_attempts or 0)),
            }
            return render(request, self.template_name, context)


class ResendOTPView(View):
    """Resend OTP to user phone."""
    
    def post(self, request):
        pending_user_id = request.session.get('pending_user_id')
        if not pending_user_id:
            return JsonResponse({'success': False, 'message': 'No pending verification'})
        
        user = get_object_or_404(User, id=pending_user_id)
        otp = generate_otp(user)
        # send_otp_sms(user.phone_number, otp)  # Uncomment in production
        
        return JsonResponse({
            'success': True,
            'message': f'OTP resent to {user.phone_number}',
            'expires_in': getattr(settings, 'OTP_EXPIRY_MINUTES', 10)
        })


class LogoutView(View):
    """Handle user logout."""
    
    def get(self, request):
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
        return redirect('core:home')


# =============================================================================
# Profile Views
# =============================================================================

class ProfileView(LoginRequiredMixin, TemplateView):
    """Display user profile dashboard."""
    
    template_name = 'accounts/profile.html'
    login_url = 'accounts:login'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        context['user'] = user
        context['addresses'] = user.addresses.all()[:5]
        context['order_count'] = user.orders.count()
        context['wishlist_count'] = user.wishlist_items.count()
        
        # Add vendor/rider info if applicable
        if user.role == User.Role.VENDOR and hasattr(user, 'vendor_profile'):
            context['vendor'] = user.vendor_profile
            context['product_count'] = user.vendor_profile.products.count()
        
        if user.role == User.Role.RIDER and hasattr(user, 'rider_profile'):
            context['rider'] = user.rider_profile
        
        return context


class ProfileEditView(LoginRequiredMixin, View):
    """Edit user profile."""
    
    template_name = 'accounts/profile_edit.html'
    
    def get(self, request):
        form = UserProfileForm(instance=request.user)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = UserProfileForm(instance=request.user, data=request.POST, files=request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:profile')
        
        return render(request, self.template_name, {'form': form})


class ChangePasswordView(LoginRequiredMixin, View):
    """Change user password."""
    
    template_name = 'accounts/change_password.html'
    
    def get(self, request):
        form = ChangePasswordForm(user=request.user)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = ChangePasswordForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Password changed successfully!')
            return redirect('accounts:profile')
        
        return render(request, self.template_name, {'form': form})


class PasswordResetView(View):
    """Request password reset via email."""
    
    template_name = 'accounts/password_reset.html'
    
    def get(self, request):
        form = CustomPasswordResetForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = CustomPasswordResetForm(data=request.POST)
        if form.is_valid():
            form.save(
                subject_template_name='accounts/emails/password_reset_subject.txt',
                email_template_name='accounts/emails/password_reset_email.html',
                from_email=settings.DEFAULT_FROM_EMAIL
            )
            messages.success(request, 'Password reset link sent to your email.')
            return redirect('accounts:login')
        
        return render(request, self.template_name, {'form': form})


class PasswordResetConfirmView(View):
    """Set new password after reset."""
    
    template_name = 'accounts/password_reset_confirm.html'
    
    def get(self, request, uidb64, token):
        form = CustomSetPasswordForm(user=None)  # Will be set in post
        return render(request, self.template_name, {'form': form})
    
    def post(self, request, uidb64, token):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_decode
        
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, User.DoesNotExist):
            user = None
        
        if user is not None and default_token_generator.check_token(user, token):
            form = CustomSetPasswordForm(user=user, data=request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Password reset successful! You can now login.')
                return redirect('accounts:login')
        else:
            messages.error(request, 'Invalid reset link. Please request a new one.')
            return redirect('accounts:password_reset')
        
        return render(request, self.template_name, {'form': form})


# =============================================================================
# Address Views
# =============================================================================

class AddressListView(LoginRequiredMixin, ListView):
    """List user's delivery addresses."""
    
    model = Address
    template_name = 'accounts/address_list.html'
    context_object_name = 'addresses'
    paginate_by = 10
    
    def get_queryset(self):
        return Address.objects.filter(user=self.request.user).order_by('-is_default', '-id')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['default_address'] = self.get_queryset().filter(is_default=True).first()
        return context


class AddressCreateView(LoginRequiredMixin, View):
    """Create new delivery address."""
    
    template_name = 'accounts/address_form.html'
    
    def get(self, request):
        form = AddressForm()
        return render(request, self.template_name, {'form': form, 'address': None})
    
    def post(self, request):
        form = AddressForm(data=request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            
            # Unset other default if this is default
            if address.is_default:
                Address.objects.filter(user=request.user, is_default=True).update(is_default=False)
            
            address.save()
            messages.success(request, 'Address added successfully!')
            
            # HTMX request - return partial
            if request.headers.get('HX-Request'):
                return render(request, 'accounts/partials/address_item.html', {'address': address})
            
            return redirect('accounts:address_list')
        
        return render(request, self.template_name, {'form': form, 'address': None})


class AddressUpdateView(LoginRequiredMixin, View):
    """Update existing address."""
    
    template_name = 'accounts/address_form.html'
    
    def get(self, request, pk):
        address = get_object_or_404(Address, pk=pk, user=request.user)
        form = AddressForm(instance=address)
        return render(request, self.template_name, {'form': form, 'address': address})
    
    def post(self, request, pk):
        address = get_object_or_404(Address, pk=pk, user=request.user)
        form = AddressForm(instance=address, data=request.POST)
        if form.is_valid():
            addr = form.save(commit=False)
            
            # Unset other default if this is default
            if addr.is_default:
                Address.objects.filter(user=request.user, is_default=True).exclude(pk=pk).update(is_default=False)
            
            addr.save()
            messages.success(request, 'Address updated successfully!')
            return redirect('accounts:address_list')
        
        return render(request, self.template_name, {'form': form, 'address': address})


@require_POST
@login_required
def address_delete(request, pk):
    """Delete an address via HTMX."""
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.delete()
    
    if request.headers.get('HX-Request'):
        addresses = Address.objects.filter(user=request.user).order_by('-is_default', '-id')
        return render(request, 'accounts/partials/address_list.html', {'addresses': addresses})
    
    messages.success(request, 'Address deleted.')
    return redirect('accounts:address_list')


@require_POST
@login_required
def address_set_default(request, pk):
    """Set an address as default."""
    address = get_object_or_404(Address, pk=pk, user=request.user)
    
    # Unset other defaults
    Address.objects.filter(user=request.user, is_default=True).update(is_default=False)
    
    address.is_default = True
    address.save(update_fields=['is_default'])
    
    if request.headers.get('HX-Request'):
        addresses = Address.objects.filter(user=request.user).order_by('-is_default', '-id')
        return render(request, 'accounts/partials/address_list.html', {'addresses': addresses})
    
    messages.success(request, 'Default address updated.')
    return redirect('accounts:address_list')


# =============================================================================
# Vendor Views
# =============================================================================

class VendorRegisterView(LoginRequiredMixin, View):
    """Register as a vendor."""
    
    template_name = 'accounts/vendor_register.html'
    
    def get(self, request):
        if request.user.role == User.Role.VENDOR:
            return redirect('accounts:vendor_status')
        
        form = VendorRegistrationForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = VendorRegistrationForm(data=request.POST, files=request.FILES)
        if form.is_valid():
            vendor = form.save(commit=False)
            vendor.user = request.user
            vendor.save()
            
            # Update user role
            request.user.role = User.Role.VENDOR
            request.user.save(update_fields=['role'])
            
            messages.success(request, 'Vendor registration submitted! Your application is under review.')
            return redirect('accounts:vendor_status')
        
        return render(request, self.template_name, {'form': form})


class VendorAgreementView(TemplateView):
    """Display vendor agreement."""
    
    template_name = 'accounts/vendor_agreement.html'


class VendorStatusView(LoginRequiredMixin, TemplateView):
    """Show vendor application status."""
    
    template_name = 'accounts/vendor_status.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if hasattr(self.request.user, 'vendor_profile'):
            context['vendor'] = self.request.user.vendor_profile
        return context


class VendorDashboardView(LoginRequiredMixin, TemplateView):
    """Vendor dashboard with stats and actions."""
    
    template_name = 'accounts/vendor_dashboard.html'
    login_url = 'accounts:login'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if not hasattr(self.request.user, 'vendor_profile'):
            raise PermissionDenied("You are not a vendor.")
        
        vendor = self.request.user.vendor_profile
        context['vendor'] = vendor
        context['products'] = vendor.products.filter(is_active=True).order_by('-created_at')[:10]
        context['recent_orders'] = vendor.order_items.select_related('order').order_by('-order__placed_at')[:5]
        
        # Stats
        total_sales = vendor.order_items.filter(
            item_status='delivered'
        ).aggregate(total=Sum('unit_price'))['total'] or 0
        
        context['stats'] = {
            'total_products': vendor.products.count(),
            'total_sales': total_sales,
            'pending_orders': vendor.order_items.filter(item_status__in=['pending', 'confirmed', 'preparing']).count(),
            'average_rating': vendor.average_rating,
        }
        
        return context


class VendorProfileEditView(LoginRequiredMixin, View):
    """Edit vendor profile."""
    
    template_name = 'accounts/vendor_profile_edit.html'
    
    def get(self, request):
        if not hasattr(request.user, 'vendor_profile'):
            raise PermissionDenied("You are not a vendor.")
        
        form = VendorProfileEditForm(instance=request.user.vendor_profile)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        if not hasattr(request.user, 'vendor_profile'):
            raise PermissionDenied("You are not a vendor.")
        
        form = VendorProfileEditForm(instance=request.user.vendor_profile, data=request.POST, files=request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Shop profile updated!')
            return redirect('accounts:vendor_dashboard')
        
        return render(request, self.template_name, {'form': form})


# =============================================================================
# Rider Views
# =============================================================================

class RiderRegisterView(LoginRequiredMixin, View):
    """Register as a delivery rider."""
    
    template_name = 'accounts/rider_register.html'
    
    def get(self, request):
        if request.user.role == User.Role.RIDER:
            return redirect('accounts:rider_dashboard')
        
        form = RiderRegistrationForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = RiderRegistrationForm(data=request.POST)
        if form.is_valid():
            rider = form.save(commit=False)
            rider.user = request.user
            rider.save()
            
            request.user.role = User.Role.RIDER
            request.user.save(update_fields=['role'])
            
            messages.success(request, 'Rider registration submitted!')
            return redirect('accounts:rider_dashboard')
        
        return render(request, self.template_name, {'form': form})


class RiderDashboardView(LoginRequiredMixin, TemplateView):
    """Rider dashboard with stats and tasks."""
    
    template_name = 'accounts/rider_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if not hasattr(self.request.user, 'rider_profile'):
            raise PermissionDenied("You are not a rider.")
        
        rider = self.request.user.rider_profile
        
        # Get available deliveries in zone
        available_deliveries = rider.current_zone.deliveries.filter(
            status='unassigned'
        ).select_related('order', 'order__customer', 'order__delivery_address') if rider.current_zone else []
        
        context['rider'] = rider
        context['available_deliveries'] = available_deliveries
        context['my_deliveries'] = rider.deliveries.select_related('order').order_by('-assigned_at')[:10]
        
        context['stats'] = {
            'total_deliveries': rider.total_deliveries,
            'available': rider.is_available,
            'current_zone': rider.current_zone.name if rider.current_zone else 'Not set',
        }
        
        return context


class RiderProfileEditView(LoginRequiredMixin, View):
    """Edit rider profile."""
    
    template_name = 'accounts/rider_profile_edit.html'
    
    def get(self, request):
        if not hasattr(request.user, 'rider_profile'):
            raise PermissionDenied("You are not a rider.")
        
        form = RiderProfileEditForm(instance=request.user.rider_profile)
        return render(request, self.template_name, {'form': form, 'rider': request.user.rider_profile})
    
    def post(self, request):
        if not hasattr(request.user, 'rider_profile'):
            raise PermissionDenied("You are not a rider.")
        
        form = RiderProfileEditForm(instance=request.user.rider_profile, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated!')
            return redirect('accounts:rider_dashboard')
        
        return render(request, self.template_name, {'form': form, 'rider': request.user.rider_profile})


# =============================================================================
# HTMX Partial Views
# =============================================================================

@login_required
def profile_dropdown_partial(request):
    """Return profile dropdown for HTMX update."""
    user = request.user
    return render(request, 'accounts/partials/profile_dropdown.html', {'user': user})
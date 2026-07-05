"""
Views for core app.
Handles homepage, about, contact, static pages, and search.
"""
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import TemplateView, View

from apps.catalog.models import Category, Product
from apps.catalog.services import get_featured_products, get_new_arrivals, search_products
from apps.support.services import get_faq_categories


# =============================================================================
# Homepage
# =============================================================================

class HomeView(TemplateView):
    """Homepage with featured products and categories."""
    
    template_name = 'core/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Featured products
        context['featured_products'] = get_featured_products(limit=8)
        
        # New arrivals
        context['new_arrivals'] = get_new_arrivals(limit=12)
        
        # Categories with product counts
        categories = Category.objects.filter(
            is_active=True,
            parent__isnull=True
        ).prefetch_related('children')[:8]
        
        for cat in categories:
            cat.product_count = cat.products.filter(is_active=True).count()
        
        context['categories'] = categories
        
        return context


# =============================================================================
# Static Pages
# =============================================================================

class AboutView(TemplateView):
    """About page."""
    template_name = 'core/about.html'


class ContactView(TemplateView):
    """Contact page with form."""
    template_name = 'core/contact.html'
    
    def post(self, request):
        name = request.POST.get('name', '')
        email = request.POST.get('email', '')
        subject = request.POST.get('subject', '')
        message_text = request.POST.get('message', '')
        
        if name and email and subject and message_text:
            # In production, would send email or create ticket
            messages.success(request, 'Thank you for your message! We will get back to you soon.')
        else:
            messages.error(request, 'Please fill in all fields.')
        
        return render(request, self.template_name)


class ReturnPolicyView(TemplateView):
    """Return policy page."""
    template_name = 'core/return_policy.html'


class PrivacyView(TemplateView):
    """Privacy policy page."""
    template_name = 'core/privacy.html'


class TermsView(TemplateView):
    """Terms of service page."""
    template_name = 'core/terms.html'


class FAQView(TemplateView):
    """FAQ page."""
    template_name = 'core/faq.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['faq_categories'] = get_faq_categories()
        return context


# =============================================================================
# Search
# =============================================================================

class SearchResultsView(View):
    """Search results page."""
    
    template_name = 'core/search_results.html'
    
    def get(self, request):
        query = request.GET.get('q', '').strip()
        page = request.GET.get('page', 1)
        
        if len(query) < 2:
            return render(request, self.template_name, {
                'query': query,
                'results': [],
                'total_count': 0,
                'categories': Category.objects.filter(is_active=True)[:10],
            })
        
        # Perform search
        results = search_products(
            query=query,
            page=int(page),
            per_page=12
        )
        
        # Get categories for filter
        categories = Category.objects.filter(is_active=True)[:10]
        
        context = {
            'query': query,
            'results': results['results'],
            'total_count': results['total_count'],
            'page': results['page'],
            'total_pages': results['total_pages'],
            'categories': categories,
        }
        
        return render(request, self.template_name, context)


# =============================================================================
# HTMX Search Suggestions
# =============================================================================

def search_suggestions_htmx(request):
    """Return search suggestions as user types (HTMX)."""
    query = request.GET.get('q', '')
    
    if len(query) < 2:
        return render(request, 'core/partials/search_suggestions.html', {'suggestions': []})
    
    # Get product suggestions
    products = Product.objects.filter(
        is_active=True,
        name__icontains=query
    ).values_list('name', flat=True)[:5]
    
    # Get category suggestions
    categories = Category.objects.filter(
        is_active=True,
        name__icontains=query
    ).values_list('name', flat=True)[:3]
    
    suggestions = {
        'products': list(products),
        'categories': list(categories),
    }
    
    return render(request, 'core/partials/search_suggestions.html', {'suggestions': suggestions})
"""
Services for orders app.
Business logic for cart, checkout, orders, payments, and delivery fee calculation.
"""
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from .models import Cart, CartItem, Coupon, Order, OrderItem, Transaction, VendorPayout


# =============================================================================
# Cart Services
# =============================================================================

def get_or_create_cart(user=None, session_key=None):
    """
    Get or create a cart for the user or session.
    """
    if user:
        cart, created = Cart.objects.get_or_create(user=user)
    elif session_key:
        cart, created = Cart.objects.get_or_create(session_key=session_key)
    else:
        return None
    
    return cart


def get_cart_items(user=None, session_key=None):
    """Get all items in the cart."""
    cart = get_or_create_cart(user=user, session_key=session_key)
    if not cart:
        return []
    
    return CartItem.objects.filter(cart=cart).select_related(
        'product', 'product__vendor', 'product__category'
    ).prefetch_related('product__images', 'variant')


def get_cart_total(user=None, session_key=None):
    """Calculate cart subtotal."""
    items = get_cart_items(user=user, session_key=session_key)
    total = Decimal('0.00')
    
    for item in items:
        price = item.variant.effective_price if item.variant else item.product.effective_price
        total += price * item.quantity
    
    return total


def add_to_cart(user, product, quantity=1, variant=None):
    """
    Add product to cart.
    If product already in cart, update quantity.
    """
    cart = get_or_create_cart(user=user)
    
    # Check stock
    from apps.catalog.services import check_product_available
    if not check_product_available(product, quantity, variant):
        return None, "Not enough stock available"
    
    # Get or create cart item
    try:
        item = CartItem.objects.get(
            cart=cart,
            product=product,
            variant=variant
        )
        item.quantity += quantity
        item.save(update_fields=['quantity'])
    except CartItem.DoesNotExist:
        item = CartItem.objects.create(
            cart=cart,
            product=product,
            variant=variant,
            quantity=quantity
        )
    
    return item, None


def update_cart_item(item_id, quantity):
    """Update cart item quantity."""
    try:
        item = CartItem.objects.get(id=item_id)
        
        if quantity <= 0:
            item.delete()
            return None, None
        else:
            # Check stock
            from apps.catalog.services import check_product_available
            if not check_product_available(item.product, quantity, item.variant):
                return item, "Not enough stock available"
            
            item.quantity = quantity
            item.save(update_fields=['quantity'])
            return item, None
    except CartItem.DoesNotExist:
        return None, "Item not found"


def remove_from_cart(item_id):
    """Remove item from cart."""
    try:
        item = CartItem.objects.get(id=item_id)
        item.delete()
        return True, None
    except CartItem.DoesNotExist:
        return False, "Item not found"


def clear_cart(user=None, session_key=None):
    """Clear all items from cart."""
    cart = get_or_create_cart(user=user, session_key=session_key)
    if cart:
        cart.items.all().delete()
    return True


def merge_guest_cart(user, session_key):
    """
    Merge guest cart into user cart on login.
    """
    try:
        guest_cart = Cart.objects.get(session_key=session_key)
    except Cart.DoesNotExist:
        return
    
    user_cart = get_or_create_cart(user=user)
    
    if not guest_cart.items.exists():
        return
    
    for guest_item in guest_cart.items.all():
        try:
            # Check if product already in user cart
            user_item = CartItem.objects.get(
                cart=user_cart,
                product=guest_item.product,
                variant=guest_item.variant
            )
            # Merge quantities
            user_item.quantity += guest_item.quantity
            user_item.save(update_fields=['quantity'])
        except CartItem.DoesNotExist:
            # Move item to user cart
            guest_item.cart = user_cart
            guest_item.save(update_fields=['cart'])
    
    # Delete guest cart
    guest_cart.delete()


# =============================================================================
# Delivery Fee Calculation
# =============================================================================

def calculate_delivery_fee(address):
    """
    Calculate delivery fee based on address zone.
    """
    from apps.delivery.models import DeliveryZone
    
    try:
        zone = DeliveryZone.objects.filter(
            is_active=True,
            ward_numbers__contains=address.ward_number
        ).first()
        
        if zone:
            return {
                'deliverable': True,
                'fee': zone.base_delivery_fee,
                'estimated_minutes': zone.estimated_delivery_time_minutes,
                'zone_name': zone.name,
            }
    except Exception:
        pass
    
    return {
        'deliverable': False,
        'fee': Decimal('0.00'),
        'estimated_minutes': 0,
        'message': 'Delivery not available to this address'
    }


# =============================================================================
# Coupon Services
# =============================================================================

def validate_coupon(code, user, order_total):
    """
    Validate a coupon code.
    Returns (coupon, error_message)
    """
    code = code.strip().upper()
    
    try:
        coupon = Coupon.objects.get(code=code, is_active=True)
    except Coupon.DoesNotExist:
        return None, "Invalid coupon code"
    
    now = timezone.now()
    
    # Check validity period
    if coupon.valid_from and coupon.valid_from > now:
        return None, "This coupon is not yet active"
    
    if coupon.valid_until and coupon.valid_until < now:
        return None, "This coupon has expired"
    
    # Check minimum order amount
    if coupon.minimum_order_amount and order_total < coupon.minimum_order_amount:
        return None, f"Minimum order amount is NPR {coupon.minimum_order_amount}"
    
    # Check usage limit
    if coupon.max_uses:
        used_count = coupon.orders.count()
        if used_count >= coupon.max_uses:
            return None, "This coupon has reached its usage limit"
    
    # Check per-user limit
    if coupon.orders.filter(customer=user).exists():
        return None, "You have already used this coupon"
    
    return coupon, None


def calculate_discount(coupon, order_total):
    """Calculate discount amount based on coupon type."""
    if coupon.discount_type == 'percentage':
        discount = order_total * (coupon.discount_value / 100)
        # Cap at order total
        return min(discount, order_total)
    else:  # fixed
        return min(coupon.discount_value, order_total)


# =============================================================================
# Order Placement
# =============================================================================

@transaction.atomic
def place_order(user, address, payment_method, coupon_code=None, special_instructions=''):
    """
    Place an order from the cart.
    Creates order, order items, and initiates payment.
    """
    cart_items = list(get_cart_items(user=user))
    
    if not cart_items:
        return None, "Your cart is empty"
    
    # Calculate totals
    subtotal = get_cart_total(user=user)
    
    # Delivery fee
    delivery_info = calculate_delivery_fee(address)
    if not delivery_info['deliverable']:
        return None, delivery_info.get('message', 'Delivery not available')
    
    delivery_fee = delivery_info['fee']
    
    # Coupon discount
    discount_amount = Decimal('0.00')
    coupon = None
    
    if coupon_code:
        coupon, error = validate_coupon(coupon_code, user, subtotal)
        if error:
            return None, error
        discount_amount = calculate_discount(coupon, subtotal)
    
    total_amount = subtotal + delivery_fee - discount_amount
    
    # Create order
    order = Order.objects.create(
        customer=user,
        delivery_address=address,
        status=Order.Status.PENDING,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        discount_amount=discount_amount,
        coupon=coupon,
        total_amount=total_amount,
        payment_method=payment_method,
        payment_status=Order.PaymentStatus.PENDING,
        special_instructions=special_instructions
    )
    
    # Create order items (snapshot current price and commission)
    for cart_item in cart_items:
        unit_price = cart_item.variant.effective_price if cart_item.variant else cart_item.product.effective_price
        commission_amount = unit_price * cart_item.quantity * cart_item.product.vendor.commission_rate / 100
        
        OrderItem.objects.create(
            order=order,
            product=cart_item.product,
            variant=cart_item.variant,
            vendor=cart_item.product.vendor,
            quantity=cart_item.quantity,
            unit_price=unit_price,
            commission_amount=commission_amount,
            item_status=OrderItem.ItemStatus.PENDING
        )
    
    # Create transaction record
    Transaction.objects.create(
        order=order,
        gateway=payment_method,
        amount=total_amount,
        status=Transaction.Status.INITIATED
    )
    
    # Clear cart
    clear_cart(user=user)
    
    # Update vendor stats
    for cart_item in cart_items:
        from apps.catalog.services import update_product_stock
        update_product_stock(cart_item.product, -cart_item.quantity, cart_item.variant)
    
    return order, None


# =============================================================================
# Order Status Management
# =============================================================================

def update_order_status(order: Order):
    """
    Recompute order status based on item statuses.
    Called after each item status change.
    """
    items = order.items.all()
    
    # Check if all items are delivered
    all_delivered = all(item.item_status == OrderItem.ItemStatus.DELIVERED for item in items)
    if all_delivered:
        order.status = Order.Status.DELIVERED
        order.delivered_at = timezone.now()
    # Check if any item is cancelled
    elif any(item.item_status == OrderItem.ItemStatus.CANCELLED for item in items):
        all_cancelled = all(item.item_status == OrderItem.ItemStatus.CANCELLED for item in items)
        if all_cancelled:
            order.status = Order.Status.CANCELLED
        else:
            order.status = Order.Status.PARTIAL
    # Check if all items are preparing or ready
    elif all(item.item_status in [OrderItem.ItemStatus.PREPARING, OrderItem.ItemStatus.READY] for item in items):
        order.status = Order.Status.PREPARING
    
    order.save(update_fields=['status', 'delivered_at'])


@transaction.atomic
def cancel_order(order: Order, user, reason: str = None):
    """
    Cancel an order.
    Only allows cancellation if order is still pending or confirmed.
    """
    if order.status not in [Order.Status.PENDING, Order.Status.CONFIRMED]:
        return False, "This order cannot be cancelled anymore"
    
    if order.customer != user:
        return False, "You are not authorized to cancel this order"
    
    order.status = Order.Status.CANCELLED
    order.cancellation_reason = reason or ''
    order.save(update_fields=['status', 'cancellation_reason'])
    
    # Refund if already paid
    if order.payment_status == Order.PaymentStatus.PAID:
        # Mark for refund (actual refund processed by payment gateway)
        order.payment_status = Order.PaymentStatus.REFUNDED
        order.save(update_fields=['payment_status'])
        
        # Create refund transaction
        Transaction.objects.create(
            order=order,
            gateway=order.payment_method,
            amount=order.total_amount,
            status=Transaction.Status.REFUNDED
        )
    
    # Restore stock
    for item in order.items.all():
        from apps.catalog.services import update_product_stock
        update_product_stock(item.product, item.quantity, item.variant)
    
    return True, None


# =============================================================================
# Payment Processing
# =============================================================================

def initiate_esewa_payment(order: Order):
    """
    Initiate eSewa payment.
    Returns payment URL and reference ID.
    """
    # Placeholder for eSewa integration
    # In production, use eSewa API
    import uuid
    
    ref_id = f"MM-{order.id}-{uuid.uuid4().hex[:6].upper()}"
    
    # Update transaction
    order.transactions.update_or_create(
        gateway='esewa',
        defaults={'gateway_transaction_id': ref_id}
    )
    
    # Return eSewa payment URL
    # In production: return eSewa endpoint with appropriate parameters
    return f"https://uat.esewa.com.np/epay/transact?amt={order.total_amount}&pid={ref_id}&su=success&fu=failure"


def initiate_khalti_payment(order: Order):
    """
    Initiate Khalti payment.
    Returns payment URL and reference ID.
    """
    import uuid
    
    ref_id = f"MM-{order.id}-{uuid.uuid4().hex[:6].upper()}"
    
    order.transactions.update_or_create(
        gateway='khalti',
        defaults={'gateway_transaction_id': ref_id}
    )
    
    # Return Khalti payment URL
    return f"https://khalti.com/payment?amount={order.total_amount * 100}&product_identity={ref_id}"


@transaction.atomic
def process_payment_callback(order: Order, gateway: str, status: str, transaction_id: str):
    """
    Process payment gateway callback.
    """
    try:
        transaction = order.transactions.get(gateway=gateway)
        transaction.gateway_transaction_id = transaction_id
        transaction.status = Transaction.Status.SUCCESS if status == 'success' else Transaction.Status.FAILED
        transaction.save()
        
        if status == 'success':
            order.payment_status = Order.PaymentStatus.PAID
            order.status = Order.Status.CONFIRMED
            order.confirmed_at = timezone.now()
            order.save(update_fields=['payment_status', 'status', 'confirmed_at'])
            
            # Update vendor order counts
            for item in order.items.all():
                from apps.accounts.services import refresh_vendor_stats
                refresh_vendor_stats(item.vendor)
            
            return True
        else:
            order.payment_status = Order.PaymentStatus.FAILED
            order.save(update_fields=['payment_status'])
            return False
    except Transaction.DoesNotExist:
        return False


# =============================================================================
# Vendor Payout Services
# =============================================================================

def calculate_vendor_payout(vendor, period_start, period_end):
    """
    Calculate payout for a vendor in a given period.
    """
    items = OrderItem.objects.filter(
        vendor=vendor,
        item_status='delivered',
        order__placed_at__date__gte=period_start,
        order__placed_at__date__lte=period_end
    )
    
    gross_sales = items.aggregate(total=Sum('unit_price'))['total'] or Decimal('0.00')
    commission_deducted = items.aggregate(total=Sum('commission_amount'))['total'] or Decimal('0.00')
    net_payout = gross_sales - commission_deducted
    
    return {
        'gross_sales': gross_sales,
        'commission_deducted': commission_deducted,
        'net_payout': net_payout,
        'item_count': items.count(),
    }


def create_vendor_payout(vendor, period_start, period_end):
    """
    Create a vendor payout record.
    """
    calc = calculate_vendor_payout(vendor, period_start, period_end)
    
    if calc['item_count'] == 0:
        return None
    
    payout = VendorPayout.objects.create(
        vendor=vendor,
        period_start=period_start,
        period_end=period_end,
        gross_sales=calc['gross_sales'],
        commission_deducted=calc['commission_deducted'],
        net_payout=calc['net_payout'],
        status=VendorPayout.Status.PENDING
    )
    
    return payout
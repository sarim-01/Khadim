import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/services/payment_service.dart';
import 'package:khaadim/services/auth_service.dart';
import 'package:khaadim/screens/payments/payment_method_screen.dart';
import 'package:khaadim/screens/orders/order_confirmation_screen.dart';
import 'package:khaadim/widgets/mic_button.dart';
import 'package:khaadim/widgets/voice_nav_callbacks.dart';
import 'package:khaadim/widgets/voice_order_handler.dart';

class CheckoutScreen extends StatefulWidget {
  final String initialPaymentMethod;

  const CheckoutScreen({
    super.key,
    this.initialPaymentMethod = 'COD',
  });

  @override
  State<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends State<CheckoutScreen> {
  final TextEditingController _address = TextEditingController();

  bool _placingOrder = false;
  String _statusText = 'Place Order';

  String _selectedPaymentMethod = 'COD';
  int? _selectedCardId;

  static const double _deliveryFee = 150;
  static const double _taxRate = 0.05;

  // ── Voice ─────────────────────────────────────────────────────
  late final VoiceOrderHandler _voiceHandler;

  @override
  void initState() {
    super.initState();
    _selectedPaymentMethod =
        widget.initialPaymentMethod.toUpperCase().contains('CARD')
            ? 'CARD'
            : 'COD';

    // ── Wire voice handler ─────────────────────────────────────
    _voiceHandler = VoiceOrderHandler();
    _voiceHandler.init();
    _voiceHandler.setNavCallbacks(
      VoiceNavCallbacks(
        switchTab: (_) {},
        openMenuWithFilter: ({String? cuisine, String? category}) =>
            Navigator.pop(context),
        openCart: () => Navigator.pop(context),
        openCheckout: ({String paymentMethod = 'COD'}) {
          // Already on checkout — just apply the payment method.
          _applyPaymentMethod(paymentMethod);
        },
        openOrders: () => Navigator.pop(context),
        openFavourites: () => Navigator.pop(context),
        openRecommendations: () => Navigator.pop(context),
        openDealsWithFilter: ({
          String? cuisineFilter,
          String? servingFilter,
          int? highlightDealId,
        }) =>
            Navigator.pop(context),
      ),
    );
    // Intercept raw transcripts to handle checkout-specific commands
    // BEFORE the generic voice pipeline gets them.
    _voiceHandler.setCheckoutInterceptor(_handleVoiceCheckout);

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final cart = context.read<CartProvider>();
      if (cart.cartId != null) {
        await cart.sync();
      }
      _loadProfileAddress();
    });
  }

  @override
  void dispose() {
    _voiceHandler.dispose();
    _address.dispose();
    super.dispose();
  }

  // ── Checkout voice interceptor ─────────────────────────────────
  // Returns true if the command was fully handled here (prevents the
  // generic voice pipeline from also speaking a reply).
  bool _handleVoiceCheckout(String transcript) {
    final t = transcript.toLowerCase().trim();

    // ── Payment method selection ───────────────────────────────
    final isCod = t.contains('cash') ||
        t.contains('cod') ||
        t.contains('کیش') ||
        t.contains('نقد') ||
        t.contains('ڈلیوری پر') ||
        t.contains('گھر پر') ||
        t.contains('delivery par') ||
        t.contains('cash on delivery');

    final isCard = t.contains('card') ||
        t.contains('کارڈ') ||
        t.contains('online') ||
        t.contains('digital') ||
        t.contains('credit') ||
        t.contains('debit');

    if (isCod && !isCard) {
      _applyPaymentMethod('COD');
      _voiceHandler.speakDirectly(
        'کیش آن ڈیلیوری منتخب کر لیا۔',
        lang: 'ur',
      );
      return true;
    }

    if (isCard && !isCod) {
      _applyPaymentMethod('CARD');
      _voiceHandler.speakDirectly(
        'کارڈ پیمنٹ منتخب کر لی۔',
        lang: 'ur',
      );
      // Push the card selector so user can pick a card.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _selectPaymentMethod();
      });
      return true;
    }

    // ── Place order ────────────────────────────────────────────
    final isPlaceOrder = t.contains('place order') ||
        t.contains('order karo') ||
        t.contains('order kar do') ||
        t.contains('آرڈر') ||
        t.contains('confirm') ||
        t.contains('کنفرم') ||
        t.contains('پیسے ادا') ||
        t.contains('submit');

    if (isPlaceOrder) {
      _voiceHandler.speakDirectly('آرڈر دے رہے ہیں۔', lang: 'ur');
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && !_placingOrder) _placeOrder();
      });
      return true;
    }

    return false; // let the generic pipeline handle it
  }

  void _applyPaymentMethod(String method) {
    setState(() {
      _selectedPaymentMethod = method.toUpperCase() == 'CARD' ? 'CARD' : 'COD';
      _selectedCardId = null;
    });
  }

  Future<void> _loadProfileAddress() async {
    try {
      final res = await AuthService.me();
      final user = res['user'] as Map<String, dynamic>? ?? {};
      if (mounted) {
        final savedAddress = user['delivery_address']?.toString() ?? '';
        if (savedAddress.isNotEmpty) {
          setState(() => _address.text = savedAddress);
        }
      }
    } catch (_) {
      // Ignore if it fails, let them type it manually
    }
  }

  Future<void> _selectPaymentMethod() async {
    final result = await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => const PaymentMethodsScreen(),
      ),
    );

    if (result == null || result is! Map) return;

    setState(() {
      _selectedPaymentMethod = (result['payment_method'] ?? 'COD').toString();
      _selectedCardId = result['card_id'] as int?;
    });
  }

  Future<void> _placeOrder() async {
    if (_placingOrder) return;

    final cart = context.read<CartProvider>();

    if (cart.cartId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text("Cart not initialized. Please login again."),
        ),
      );
      return;
    }

    if (cart.items.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Your cart is empty.")),
      );
      return;
    }

    if (_address.text.trim().length < 5) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Please enter a valid delivery address.")),
      );
      return;
    }

    if (_selectedPaymentMethod == 'CARD' && _selectedCardId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Please select a card.")),
      );
      return;
    }

    setState(() {
      _placingOrder = true;
      _statusText = _selectedPaymentMethod == 'CARD'
          ? 'Processing payment…'
          : 'Placing order…';
    });

    final subtotal = cart.totalPrice;
    final tax = subtotal * _taxRate;
    final total = subtotal + tax + _deliveryFee;

    String? transactionId;

    // ── Step 1: Process payment only for CARD ─────────────────────
    if (_selectedPaymentMethod == 'CARD') {
      try {
        final payRes = await PaymentService.processPayment(
          cartId: cart.cartId!,
          amount: total,
          cardId: _selectedCardId!,
        );
        transactionId = payRes['transaction_id'] as String?;
      } catch (e) {
        if (!mounted) return;

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(_readableError(e)),
            behavior: SnackBarBehavior.floating,
          ),
        );

        setState(() {
          _placingOrder = false;
          _statusText = 'Place Order';
        });
        return;
      }
    }

    // ── Step 2: Place order ───────────────────────────────────────
    setState(() => _statusText = 'Placing order…');

    try {
      final res = await CartService.placeOrder(
        cartId: cart.cartId!,
        deliveryAddress: _address.text.trim(),
        deliveryFee: _deliveryFee,
        taxRate: _taxRate,
        transactionId: transactionId,
      );

      final orderId = res["order_id"]?.toString();
      final totalNum = res["total_price"] ?? res["total"];
      final finalTotal = (totalNum is num) ? totalNum.toDouble() : total;

      await cart.refreshAfterOrderSuccess();

      if (transactionId != null && orderId != null) {
        CartService.linkPaymentToOrder(
          transactionId: transactionId,
          orderId: int.tryParse(orderId) ?? 0,
        );
      }

      if (!mounted) return;

      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => OrderConfirmationScreen(
            orderId: int.tryParse(orderId ?? '') ?? 0,
            orderNumber: orderId ?? _generateLocalOrderNumber(),
            totalAmount: finalTotal,
            estimatedPrepTimeMinutes:
                (res["estimated_prep_time_minutes"] is num)
                    ? (res["estimated_prep_time_minutes"] as num).toInt()
                    : 0,
            transactionId: transactionId,
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            transactionId != null
                ? 'Payment went through but order failed. Contact support with ID: $transactionId'
                : _readableError(e),
          ),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 6),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _placingOrder = false;
          _statusText = 'Place Order';
        });
      }
    }
  }

  String _readableError(Object e) {
    final text = e.toString().toLowerCase();
    if (text.contains("cart is empty")) return "Your cart is empty.";
    if (text.contains("cart not found")) {
      return "Your cart session expired. Please try again.";
    }
    if (text.contains("not active")) {
      return "This cart is no longer active. Please try again.";
    }
    if (text.contains("unauthorized") || text.contains("401")) {
      return "Your session expired. Please login again.";
    }
    if (text.contains("timeout")) return "Request timed out. Please try again.";
    if (text.contains("payment failed")) {
      return "Payment failed. Please try again.";
    }
    return "Could not place order. Please try again.";
  }

  String _generateLocalOrderNumber() {
    final now = DateTime.now();
    final yy = (now.year % 100).toString().padLeft(2, '0');
    final mm = now.month.toString().padLeft(2, '0');
    final dd = now.day.toString().padLeft(2, '0');
    final hh = now.hour.toString().padLeft(2, '0');
    final mi = now.minute.toString().padLeft(2, '0');
    return "KHD-$yy$mm$dd-$hh$mi";
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = theme.colorScheme;

    return PopScope(
      canPop: !_placingOrder,
      child: Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: AppBar(
          title: const Text("Checkout"),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back),
            onPressed: _placingOrder ? null : () => Navigator.pop(context),
          ),
        ),
        // ── Voice mic FAB ─────────────────────────────────────────
        floatingActionButton: AnimatedBuilder(
          animation: _voiceHandler,
          builder: (_, __) => MicButton(
            isRecording: _voiceHandler.isRecording,
            isProcessing: _voiceHandler.isProcessing,
            onPressDown: () => _voiceHandler.onMicDown(context),
            onPressUp: () => _voiceHandler.onMicUp(context),
            onCancel: _voiceHandler.onMicCancel,
          ),
        ),
        body: AbsorbPointer(
          absorbing: _placingOrder,
          child: Consumer<CartProvider>(
            builder: (context, cart, _) {
              final subtotal = cart.totalPrice;
              final tax = subtotal * _taxRate;
              final total = subtotal + tax + _deliveryFee;

              return SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // ── Voice hint banner ─────────────────────────
                    Container(
                      margin: const EdgeInsets.only(bottom: 16),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 10,
                      ),
                      decoration: BoxDecoration(
                        color: color.primary.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: color.primary.withValues(alpha: 0.25),
                        ),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.mic_none_rounded,
                              color: color.primary, size: 18),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'آواز سے کہیں: "کیش آن ڈیلیوری" یا "کارڈ سے پیمنٹ" یا "آرڈر کرو"',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: color.primary,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    _buildSectionCard(
                      context,
                      title: "Delivery Address",
                      child: TextField(
                        controller: _address,
                        enabled: !_placingOrder,
                        style: theme.textTheme.bodyMedium,
                        decoration: InputDecoration(
                          labelText: "Address",
                          labelStyle: theme.textTheme.bodySmall,
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                          filled: true,
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    _buildSectionCard(
                      context,
                      title: "Payment Method",
                      child: Column(
                        children: [
                          _PaymentChip(
                            label: 'Cash on Delivery',
                            icon: Icons.local_shipping_outlined,
                            selected: _selectedPaymentMethod == 'COD',
                            onTap: _placingOrder
                                ? null
                                : () => _applyPaymentMethod('COD'),
                          ),
                          const SizedBox(height: 8),
                          _PaymentChip(
                            label: _selectedPaymentMethod == 'CARD' &&
                                    _selectedCardId != null
                                ? 'Card Selected'
                                : 'Pay by Card',
                            icon: Icons.credit_card_outlined,
                            selected: _selectedPaymentMethod == 'CARD',
                            onTap: _placingOrder
                                ? null
                                : () async {
                                    _applyPaymentMethod('CARD');
                                    await _selectPaymentMethod();
                                  },
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                    _buildSectionCard(
                      context,
                      title: "Order Summary",
                      child: Column(
                        children: [
                          _SummaryRow(
                            "Subtotal",
                            "Rs ${subtotal.toStringAsFixed(2)}",
                          ),
                          _SummaryRow(
                            "Tax",
                            "Rs ${tax.toStringAsFixed(2)}",
                          ),
                          _SummaryRow(
                            "Delivery Fee",
                            "Rs ${_deliveryFee.toStringAsFixed(2)}",
                          ),
                          const Divider(),
                          _SummaryRow(
                            "Total",
                            "Rs ${total.toStringAsFixed(2)}",
                            isBold: true,
                            color: theme.colorScheme.onSurface,
                          ),
                          if (cart.error != null) ...[
                            const SizedBox(height: 10),
                            Text(
                              cart.error!,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.error,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                    const SizedBox(height: 24),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: (_placingOrder || cart.isSyncing)
                            ? null
                            : _placeOrder,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: color.primary,
                          foregroundColor: color.onPrimary,
                          minimumSize: const Size(double.infinity, 52),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                        ),
                        child: _placingOrder
                            ? Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  const SizedBox(
                                    height: 18,
                                    width: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      color: Colors.white,
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Text(
                                    _statusText,
                                    style: const TextStyle(color: Colors.white),
                                  ),
                                ],
                              )
                            : const Text("Place Order"),
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      ),
    );
  }

  static Widget _buildSectionCard(
    BuildContext context, {
    required String title,
    required Widget child,
  }) {
    final theme = Theme.of(context);
    return Card(
      color: theme.cardColor,
      elevation: 0.5,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
                color: theme.colorScheme.onSurface,
              ),
            ),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }
}

// ── Payment method visual chip ─────────────────────────────────────────────
class _PaymentChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback? onTap;

  const _PaymentChip({
    required this.label,
    required this.icon,
    required this.selected,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = theme.colorScheme;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color:
              selected ? color.primary.withValues(alpha: 0.12) : color.surface,
          border: Border.all(
            color:
                selected ? color.primary : color.outline.withValues(alpha: 0.4),
            width: selected ? 2 : 1,
          ),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          children: [
            Icon(icon,
                color: selected ? color.primary : theme.hintColor, size: 22),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                label,
                style: theme.textTheme.bodyLarge?.copyWith(
                  fontWeight: selected ? FontWeight.w700 : FontWeight.normal,
                  color: selected ? color.primary : theme.hintColor,
                ),
              ),
            ),
            if (selected)
              Icon(Icons.check_circle_rounded, color: color.primary, size: 20),
          ],
        ),
      ),
    );
  }
}

class _SummaryRow extends StatelessWidget {
  final String label;
  final String value;
  final bool isBold;
  final Color color;

  const _SummaryRow(
    this.label,
    this.value, {
    this.isBold = false,
    this.color = Colors.grey,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: color,
              fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
            ),
          ),
          Text(
            value,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: color,
              fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
            ),
          ),
        ],
      ),
    );
  }
}

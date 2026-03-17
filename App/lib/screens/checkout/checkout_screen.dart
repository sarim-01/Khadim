import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/services/payment_service.dart';
import 'package:khaadim/screens/payments/payment_method_screen.dart';
import 'package:khaadim/screens/orders/order_confirmation_screen.dart';

class CheckoutScreen extends StatefulWidget {
  const CheckoutScreen({super.key});

  @override
  State<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends State<CheckoutScreen> {
  final TextEditingController _address =
  TextEditingController(text: "123 Main St, City, State 12345");

  bool _placingOrder = false;
  String _statusText = 'Place Order';

  String _selectedPaymentMethod = 'COD';
  int? _selectedCardId;
  String _selectedPaymentLabel = 'Cash on Delivery';

  static const double _deliveryFee = 150;
  static const double _taxRate = 0.05;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final cart = context.read<CartProvider>();
      if (cart.cartId != null) {
        await cart.sync();
      }
    });
  }

  @override
  void dispose() {
    _address.dispose();
    super.dispose();
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

      if (_selectedPaymentMethod == 'COD') {
        _selectedPaymentLabel = 'Cash on Delivery';
      } else if (_selectedCardId != null) {
        _selectedPaymentLabel = 'Card Selected';
      } else {
        _selectedPaymentLabel = 'Card';
      }
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

    return WillPopScope(
      onWillPop: () async => !_placingOrder,
      child: Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: AppBar(
          title: const Text("Checkout"),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back),
            onPressed: _placingOrder ? null : () => Navigator.pop(context),
          ),
        ),
        floatingActionButton: FloatingActionButton(
          backgroundColor: color.primary,
          foregroundColor: color.onPrimary,
          onPressed: _placingOrder ? null : () {},
          child: const Icon(Icons.mic_none_rounded),
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
                          InkWell(
                            onTap: _placingOrder ? null : _selectPaymentMethod,
                            borderRadius: BorderRadius.circular(10),
                            child: Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                border: Border.all(
                                  color: color.primary.withOpacity(0.6),
                                ),
                                borderRadius: BorderRadius.circular(10),
                              ),
                              child: Row(
                                children: [
                                  Icon(
                                    _selectedPaymentMethod == 'COD'
                                        ? Icons.local_shipping_outlined
                                        : Icons.credit_card_outlined,
                                    color: color.primary,
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                      CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          _selectedPaymentLabel,
                                          style: theme.textTheme.bodyLarge
                                              ?.copyWith(
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                        const SizedBox(height: 2),
                                        Text(
                                          _selectedPaymentMethod == 'COD'
                                              ? 'Pay in cash when your order arrives'
                                              : 'Tap to change payment method',
                                          style: theme.textTheme.bodySmall
                                              ?.copyWith(
                                            color: theme.hintColor,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  Icon(
                                    Icons.chevron_right,
                                    color: color.primary,
                                  ),
                                ],
                              ),
                            ),
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
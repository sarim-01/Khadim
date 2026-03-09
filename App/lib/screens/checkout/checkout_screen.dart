import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/services/card_service.dart';
import 'package:khaadim/services/payment_service.dart';
import 'package:khaadim/screens/payments/add_payment_screen.dart';
import 'package:khaadim/screens/orders/order_confirmation_screen.dart';

class CheckoutScreen extends StatefulWidget {
  const CheckoutScreen({Key? key}) : super(key: key);

  @override
  State<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends State<CheckoutScreen> {
  final TextEditingController _address =
      TextEditingController(text: "123 Main St, City, State 12345");

  int _selectedIndex = 0;
  bool _placingOrder = false;
  bool _loadingCards = true;
  String _statusText = 'Place Order';

  List<Map<String, dynamic>> _cards = [];

  static const double _deliveryFee = 150;
  static const double _taxRate = 0.05;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final cart = context.read<CartProvider>();
      if (cart.cartId != null) await cart.sync();
      await _loadCards();
    });
  }

  Future<void> _loadCards() async {
    setState(() => _loadingCards = true);
    try {
      final cards = await CardService.getSavedCards();
      if (!mounted) return;
      setState(() {
        _cards = cards;
        // auto-select default card
        final defaultIdx = cards.indexWhere((c) => c['is_default'] == true);
        _selectedIndex = defaultIdx >= 0 ? defaultIdx : 0;
      });
    } catch (_) {
      // silently ignore — empty state shown
    } finally {
      if (mounted) setState(() => _loadingCards = false);
    }
  }

  Future<void> _deleteCard(int cardId) async {
    try {
      await CardService.deleteCard(cardId: cardId);
      await _loadCards();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to delete card: $e')),
      );
    }
  }

  @override
  void dispose() {
    _address.dispose();
    super.dispose();
  }

  Future<void> _placeOrder() async {
    if (_placingOrder) return;

    final cart = context.read<CartProvider>();

    if (cart.cartId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Cart not initialized. Please login again.")),
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
    if (_cards.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Please add a payment method.")),
      );
      return;
    }

    setState(() {
      _placingOrder = true;
      _statusText = 'Processing payment…';
    });

    final subtotal = cart.totalPrice;
    final tax = subtotal * _taxRate;
    final total = subtotal + tax + _deliveryFee;
    final selectedCard = _cards[_selectedIndex];
    final cardId = selectedCard['card_id'] as int;

    String? transactionId;

    // ── Step 1: Process payment ─────────────────────────────────
    try {
      final payRes = await PaymentService.processPayment(
        cartId: cart.cartId!,
        amount: total,
        cardId: cardId,
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

    // ── Step 2: Place order ─────────────────────────────────────
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
      final finalTotal =
          (totalNum is num) ? totalNum.toDouble() : total;

      await cart.refreshAfterOrderSuccess();

      // Fire-and-forget: link payment to order
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
    if (text.contains("cart not found")) return "Your cart session expired. Please try again.";
    if (text.contains("not active")) return "This cart is no longer active. Please try again.";
    if (text.contains("unauthorized") || text.contains("401")) {
      return "Your session expired. Please login again.";
    }
    if (text.contains("timeout")) return "Request timed out. Please try again.";
    if (text.contains("payment failed")) return "Payment failed. Please try again.";
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
                    // ── Delivery Address ──────────────────────
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
                              borderRadius: BorderRadius.circular(10)),
                          filled: true,
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),

                    // ── Payment Method ────────────────────────
                    _buildSectionCard(
                      context,
                      title: "Payment Method",
                      child: _loadingCards
                          ? const Padding(
                              padding: EdgeInsets.symmetric(vertical: 16),
                              child: Center(child: CircularProgressIndicator()),
                            )
                          : Column(
                              children: [
                                if (_cards.isEmpty)
                                  Padding(
                                    padding: const EdgeInsets.only(bottom: 10),
                                    child: Text(
                                      "No payment methods yet. Add one to proceed.",
                                      style: theme.textTheme.bodyMedium
                                          ?.copyWith(color: theme.hintColor),
                                    ),
                                  ),
                                for (int i = 0; i < _cards.length; i++)
                                  _buildPaymentTile(
                                    context,
                                    "${_cards[i]['card_type']} •••• ${_cards[i]['last4']}",
                                    "Expires ${_cards[i]['expiry']}",
                                    selected: _selectedIndex == i,
                                    onTap: _placingOrder
                                        ? () {}
                                        : () => setState(() => _selectedIndex = i),
                                    onDelete: _placingOrder
                                        ? null
                                        : () => _deleteCard(
                                            _cards[i]['card_id'] as int),
                                  ),
                                const SizedBox(height: 12),
                                OutlinedButton.icon(
                                  onPressed: _placingOrder
                                      ? null
                                      : () async {
                                          final result = await Navigator.push(
                                            context,
                                            MaterialPageRoute(
                                              builder: (_) =>
                                                  const AddPaymentScreen(),
                                            ),
                                          );
                                          if (result != null &&
                                              result is Map) {
                                            await _loadCards();
                                          }
                                        },
                                  icon: Icon(Icons.add, color: color.primary),
                                  label: Text(
                                    "Add New Payment Method",
                                    style: TextStyle(color: color.primary),
                                  ),
                                  style: OutlinedButton.styleFrom(
                                    side: BorderSide(color: color.primary),
                                    foregroundColor: color.primary,
                                    minimumSize:
                                        const Size(double.infinity, 48),
                                  ),
                                ),
                              ],
                            ),
                    ),
                    const SizedBox(height: 16),

                    // ── Order Summary ─────────────────────────
                    _buildSectionCard(
                      context,
                      title: "Order Summary",
                      child: Column(
                        children: [
                          _SummaryRow(
                              "Subtotal", "Rs ${subtotal.toStringAsFixed(2)}"),
                          _SummaryRow("Tax", "Rs ${tax.toStringAsFixed(2)}"),
                          _SummaryRow("Delivery Fee",
                              "Rs ${_deliveryFee.toStringAsFixed(2)}"),
                          const Divider(),
                          _SummaryRow(
                            "Total",
                            "Rs ${total.toStringAsFixed(2)}",
                            isBold: true,
                            color: theme.colorScheme.onBackground,
                          ),
                          if (cart.error != null) ...[
                            const SizedBox(height: 10),
                            Text(
                              cart.error!,
                              style: theme.textTheme.bodySmall?.copyWith(
                                  color: theme.colorScheme.error),
                            ),
                          ],
                        ],
                      ),
                    ),
                    const SizedBox(height: 24),

                    // ── Confirm Button ────────────────────────
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
                              borderRadius: BorderRadius.circular(10)),
                        ),
                        child: _placingOrder
                            ? Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  const SizedBox(
                                    height: 18,
                                    width: 18,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2, color: Colors.white),
                                  ),
                                  const SizedBox(width: 12),
                                  Text(_statusText,
                                      style: const TextStyle(
                                          color: Colors.white)),
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

  // ── Helper Widgets ──────────────────────────────────────────────

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
                  color: theme.colorScheme.onBackground),
            ),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }

  static Widget _buildPaymentTile(
    BuildContext context,
    String title,
    String subtitle, {
    required bool selected,
    required VoidCallback onTap,
    VoidCallback? onDelete,
  }) {
    final theme = Theme.of(context);
    final color = theme.colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        border: Border.all(
          color: selected ? color.primary : color.primary.withOpacity(0.4),
        ),
        borderRadius: BorderRadius.circular(10),
      ),
      child: ListTile(
        leading: Icon(Icons.credit_card_outlined, color: color.primary),
        title: Text(title,
            style: theme.textTheme.bodyLarge
                ?.copyWith(fontWeight: FontWeight.w600)),
        subtitle: Text(subtitle,
            style:
                theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (selected) Icon(Icons.check_circle, color: color.primary),
            if (onDelete != null)
              IconButton(
                icon: Icon(Icons.delete_outline, color: color.error, size: 20),
                onPressed: onDelete,
              ),
          ],
        ),
        onTap: onTap,
      ),
    );
  }
}

class _SummaryRow extends StatelessWidget {
  final String label, value;
  final bool isBold;
  final Color color;

  const _SummaryRow(
    this.label,
    this.value, {
    this.isBold = false,
    this.color = Colors.grey,
    Key? key,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label,
              style: theme.textTheme.bodyMedium?.copyWith(
                  color: color,
                  fontWeight:
                      isBold ? FontWeight.bold : FontWeight.normal)),
          Text(value,
              style: theme.textTheme.bodyMedium?.copyWith(
                  color: color,
                  fontWeight:
                      isBold ? FontWeight.bold : FontWeight.normal)),
        ],
      ),
    );
  }
}

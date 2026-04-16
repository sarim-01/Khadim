import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:khaadim/services/upsell_service.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/providers/cart_provider.dart';

class UpsellPopup extends StatefulWidget {
  const UpsellPopup({super.key});

  @override
  State<UpsellPopup> createState() => _UpsellPopupState();
}

class _UpsellPopupState extends State<UpsellPopup> {
  UpsellResult? _result;
  bool _loading = true;
  String? _error;

  // Track which item ids are being added
  final Set<int> _adding = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final result = await UpsellService.fetchUpsell();
      if (mounted) setState(() { _result = result; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Future<void> _addToCart(BuildContext context, UpsellItem item) async {
    final cart = Provider.of<CartProvider>(context, listen: false);
    if (cart.cartId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Cart not ready, please wait.")),
      );
      return;
    }

    setState(() => _adding.add(item.itemId));
    try {
      await CartService.addItem(
        cartId: cart.cartId!,
        itemType: "menu_item",
        itemId: item.itemId,
        quantity: 1,
      );
      await cart.sync();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text("${item.itemName} added to cart!"),
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 1),
          ),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Failed to add ${item.itemName}")),
        );
      }
    } finally {
      if (mounted) setState(() => _adding.remove(item.itemId));
    }
  }

  Widget _weatherIcon(String category) {
    final icons = {
      'hot': Icons.wb_sunny_rounded,
      'cold': Icons.ac_unit_rounded,
      'rainy': Icons.umbrella_rounded,
      'mild': Icons.cloud_outlined,
    };
    return Icon(
      icons[category] ?? Icons.wb_sunny_rounded,
      color: const Color(0xFFD4AF37),
      size: 20,
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 40),
      child: Container(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.75,
        ),
        decoration: BoxDecoration(
          color: const Color(0xFF121318),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: const Color(0xFFD4AF37).withOpacity(0.3),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.5),
              blurRadius: 20,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Header
            Container(
              padding: const EdgeInsets.fromLTRB(20, 20, 16, 16),
              decoration: const BoxDecoration(
                border: Border(
                  bottom: BorderSide(color: Color(0xFF2A2A2A)),
                ),
              ),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: const Color(0xFFD4AF37).withOpacity(0.15),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(
                      Icons.auto_awesome,
                      color: Color(0xFFD4AF37),
                      size: 20,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      "Just for You",
                      style: theme.textTheme.bodyLarge?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: Color(0xFFB0B0B0), size: 20),
                    onPressed: () => Navigator.of(context).pop(),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                  ),
                ],
              ),
            ),

            // Body
            Flexible(
              child: _loading
                  ? const Padding(
                      padding: EdgeInsets.all(40),
                      child: CircularProgressIndicator(
                        color: Color(0xFFD4AF37),
                      ),
                    )
                  : _error != null || _result == null || _result!.items.isEmpty
                      ? Padding(
                          padding: const EdgeInsets.all(32),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.cloud_off, color: Color(0xFFB0B0B0), size: 40),
                              const SizedBox(height: 12),
                              Text(
                                "No recommendations right now",
                                style: theme.textTheme.bodyMedium,
                                textAlign: TextAlign.center,
                              ),
                            ],
                          ),
                        )
                      : SingleChildScrollView(
                          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // Headline
                              Row(
                                children: [
                                  _weatherIcon(_result!.weatherCategory),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      _result!.headline,
                                      style: theme.textTheme.bodyMedium?.copyWith(
                                        color: const Color(0xFFD4AF37),
                                        fontStyle: FontStyle.italic,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 14),

                              // Items list
                              ..._result!.items.map((item) => _buildItemRow(context, item)),
                            ],
                          ),
                        ),
            ),

            // Footer
            Container(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
              decoration: const BoxDecoration(
                border: Border(top: BorderSide(color: Color(0xFF2A2A2A))),
              ),
              child: SizedBox(
                width: double.infinity,
                child: TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  style: TextButton.styleFrom(
                    foregroundColor: const Color(0xFFB0B0B0),
                    padding: const EdgeInsets.symmetric(vertical: 10),
                  ),
                  child: const Text(
                    "Maybe Later",
                    style: TextStyle(fontSize: 14),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildItemRow(BuildContext context, UpsellItem item) {
    final isAdding = _adding.contains(item.itemId);

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF2A2A35), width: 1),
      ),
      child: Row(
        children: [
          // Category icon
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: const Color(0xFFD4AF37).withOpacity(0.1),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(
              _categoryIcon(item.itemCategory),
              color: const Color(0xFFD4AF37),
              size: 18,
            ),
          ),
          const SizedBox(width: 12),

          // Name + price
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.itemName,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  "Rs ${item.itemPrice.toStringAsFixed(0)}",
                  style: const TextStyle(
                    color: Color(0xFFD4AF37),
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),

          // Add button
          GestureDetector(
            onTap: isAdding ? null : () => _addToCart(context, item),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                color: isAdding
                    ? const Color(0xFF2A2A2A)
                    : const Color(0xFFD4AF37),
                borderRadius: BorderRadius.circular(10),
              ),
              child: isAdding
                  ? const Padding(
                      padding: EdgeInsets.all(8),
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Color(0xFFD4AF37),
                      ),
                    )
                  : const Icon(Icons.add, color: Colors.black, size: 20),
            ),
          ),
        ],
      ),
    );
  }

  IconData _categoryIcon(String? category) {
    switch (category) {
      case 'drink': return Icons.local_drink_outlined;
      case 'starter': return Icons.restaurant_outlined;
      case 'side': return Icons.dinner_dining_outlined;
      default: return Icons.fastfood_outlined;
    }
  }
}

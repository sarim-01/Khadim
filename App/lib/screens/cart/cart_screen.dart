import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/screens/checkout/checkout_screen.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/utils/ImageResolver.dart';

class CartScreen extends StatefulWidget {
  const CartScreen({super.key});

  @override
  State<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends State<CartScreen> {
  List<Map<String, dynamic>> _recommendations = [];
  final Set<int> _addingRec = {};

  @override
  void initState() {
    super.initState();
    // On open, pull latest snapshot from server then load recommendations
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await context.read<CartProvider>().sync();
      _loadRecommendations();
    });
  }

  Future<void> _loadRecommendations() async {
    final cartId = context.read<CartProvider>().cartId;
    if (cartId == null) return;
    final recs = await CartService.fetchRecommendations(cartId: cartId);
    if (mounted) setState(() => _recommendations = recs);
  }

  Future<void> _addRecommendedItem(Map<String, dynamic> rec) async {
    final cartId = context.read<CartProvider>().cartId;
    if (cartId == null) return;
    final itemId = rec['recommended_item_id'] as int;
    setState(() => _addingRec.add(itemId));
    try {
      await CartService.addItem(
        cartId: cartId,
        itemType: 'menu_item',
        itemId: itemId,
        quantity: 1,
      );
      await context.read<CartProvider>().sync();
      if (mounted) {
        setState(() {
          _recommendations.removeWhere(
              (r) => r['recommended_item_id'] == itemId);
        });
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("${rec['recommended_name']} added to cart!"),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 1),
        ));
      }
    } catch (_) {
      // fail silently
    } finally {
      if (mounted) setState(() => _addingRec.remove(itemId));
    }
  }

  double _subtotal(List items) {
    return items.fold(0.0, (sum, x) => sum + (x.price * x.quantity));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SafeArea(
      child: Scaffold(
        appBar: AppBar(
          title: const Text("Your Cart"),
          actions: [
            Consumer<CartProvider>(
              builder: (_, cart, __) {
                if (cart.items.isEmpty) return const SizedBox.shrink();
                return IconButton(
                  icon: const Icon(Icons.refresh),
                  onPressed: cart.isSyncing ? null : () => cart.sync(),
                );
              },
            ),
          ],
        ),
        body: Consumer<CartProvider>(
          builder: (context, cart, child) {
            if (cart.isSyncing && cart.items.isEmpty) {
              return const Center(child: CircularProgressIndicator());
            }

            if (cart.error != null && cart.items.isEmpty) {
              return Center(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    cart.error!,
                    style: theme.textTheme.bodyMedium,
                    textAlign: TextAlign.center,
                  ),
                ),
              );
            }

            if (cart.items.isEmpty) {
              return const Center(
                child: Text("Your cart is empty", style: TextStyle(fontSize: 16)),
              );
            }

            final subtotal = _subtotal(cart.items);
            final tax = subtotal * 0.05;
            final deliveryFee = 150;
            final total = subtotal + tax + deliveryFee;

            return Column(
              children: [
                Expanded(
                  child: ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: cart.items.length,
                    itemBuilder: (_, index) {
                      final item = cart.items[index];

                      return Card(
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                        margin: const EdgeInsets.only(bottom: 12),
                        child: ListTile(
                          leading: ClipRRect(
                            borderRadius: BorderRadius.circular(8),
                            child: _buildItemImage(
                              item.image,
                              item.title ?? item.name ?? "Item",
                              item.id.startsWith('deal:') ? 'deal' : 'item',
                            ),
                          ),
                          title: Text(
                            item.title ?? item.name ?? "Item",
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                          subtitle: Text(
                            "Rs ${item.price}",
                            style: const TextStyle(color: Colors.grey),
                          ),
                          trailing: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              IconButton(
                                icon: const Icon(Icons.remove_circle_outline),
                                color: Colors.orangeAccent,
                                onPressed: cart.isSyncing
                                    ? null
                                    : () async {
                                  final newQty = item.quantity - 1;

                                  // item.id is "type:itemId"
                                  final parts = item.id.split(':');
                                  final type = parts.first;
                                  final id = int.tryParse(parts.last) ?? 0;

                                  if (newQty <= 0) {
                                    await cart.removeById(itemId: id, itemType: type);
                                  } else {
                                    await cart.updateQty(
                                      itemId: id,
                                      itemType: type,
                                      quantity: newQty,
                                    );
                                  }
                                },
                              ),
                              Text(
                                item.quantity.toString(),
                                style: const TextStyle(fontSize: 16),
                              ),
                              IconButton(
                                icon: const Icon(Icons.add_circle_outline),
                                color: Colors.orangeAccent,
                                onPressed: cart.isSyncing
                                    ? null
                                    : () async {
                                  final parts = item.id.split(':');
                                  final type = parts.first;
                                  final id = int.tryParse(parts.last) ?? 0;

                                  await cart.updateQty(
                                    itemId: id,
                                    itemType: type,
                                    quantity: item.quantity + 1,
                                  );
                                },
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),

                // ── Recommendations Row ──────────────────────────────
                if (_recommendations.isNotEmpty)
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 6),
                        child: Row(
                          children: [
                            const Icon(Icons.auto_awesome,
                                color: Color(0xFFD4AF37), size: 16),
                            const SizedBox(width: 6),
                            Text(
                              "Goes well with your order",
                              style: theme.textTheme.bodyMedium?.copyWith(
                                color: const Color(0xFFD4AF37),
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                      SizedBox(
                        height: 120,
                        child: ListView.builder(
                          scrollDirection: Axis.horizontal,
                          padding:
                              const EdgeInsets.symmetric(horizontal: 12),
                          itemCount: _recommendations.length,
                          itemBuilder: (_, i) {
                            final rec = _recommendations[i];
                            final itemId =
                                rec['recommended_item_id'] as int;
                            final isAdding = _addingRec.contains(itemId);
                            return Container(
                              width: 160,
                              margin: const EdgeInsets.only(right: 10),
                              padding: const EdgeInsets.all(10),
                              decoration: BoxDecoration(
                                color: theme.colorScheme.surface,
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(
                                  color: const Color(0xFFD4AF37)
                                      .withOpacity(0.3),
                                ),
                              ),
                              child: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment.start,
                                mainAxisAlignment:
                                    MainAxisAlignment.spaceBetween,
                                children: [
                                  Text(
                                    rec['recommended_name'] as String,
                                    style: const TextStyle(
                                      fontSize: 13,
                                      fontWeight: FontWeight.w600,
                                    ),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  Text(
                                    "goes well with ${rec['for_item']}",
                                    style: const TextStyle(
                                      fontSize: 11,
                                      color: Color(0xFFB0B0B0),
                                    ),
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  Row(
                                    mainAxisAlignment:
                                        MainAxisAlignment.spaceBetween,
                                    children: [
                                      Text(
                                        "Rs ${(rec['recommended_price'] as num).toStringAsFixed(0)}",
                                        style: const TextStyle(
                                          fontSize: 13,
                                          fontWeight: FontWeight.bold,
                                          color: Color(0xFFD4AF37),
                                        ),
                                      ),
                                      GestureDetector(
                                        onTap: isAdding
                                            ? null
                                            : () =>
                                                _addRecommendedItem(rec),
                                        child: AnimatedContainer(
                                          duration: const Duration(
                                              milliseconds: 200),
                                          width: 28,
                                          height: 28,
                                          decoration: BoxDecoration(
                                            color: isAdding
                                                ? const Color(0xFF2A2A2A)
                                                : const Color(0xFFD4AF37),
                                            borderRadius:
                                                BorderRadius.circular(8),
                                          ),
                                          child: isAdding
                                              ? const Padding(
                                                  padding:
                                                      EdgeInsets.all(6),
                                                  child:
                                                      CircularProgressIndicator(
                                                    strokeWidth: 2,
                                                    color: Color(0xFFD4AF37),
                                                  ),
                                                )
                                              : const Icon(Icons.add,
                                                  color: Colors.black,
                                                  size: 18),
                                        ),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                      ),
                      const SizedBox(height: 8),
                    ],
                  ),

                // ── Order Summary ────────────────────────────────────
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surface,
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.05),
                        blurRadius: 6,
                        offset: const Offset(0, -3),
                      ),
                    ],
                  ),
                  child: Column(
                    children: [
                      _buildSummaryRow("Subtotal", "Rs ${subtotal.toStringAsFixed(2)}"),
                      _buildSummaryRow("Tax", "Rs ${tax.toStringAsFixed(2)}"),
                      _buildSummaryRow("Delivery Fee", "Rs ${deliveryFee.toStringAsFixed(2)}"),
                      const Divider(),
                      _buildSummaryRow(
                        "Total",
                        "Rs ${total.toStringAsFixed(2)}",
                        isBold: true,
                        color: theme.colorScheme.onSurface,
                      ),
                      const SizedBox(height: 10),
                      ElevatedButton(
                        onPressed: (cart.isSyncing || cart.cartId == null || cart.items.isEmpty)
                            ? null
                            : () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => const CheckoutScreen()),
                          );
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.orangeAccent,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                        ),
                        child: const Text("Proceed to Checkout", style: TextStyle(fontSize: 16)),
                      ),
                    ],
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _buildItemImage(String? image, String name, String type) {
    final url = (image ?? '').trim();
    final isUrl = url.startsWith('http://') || url.startsWith('https://');

    final assetPath = type == 'deal'
        ? ImageResolver.getDealImage(name)
        : ImageResolver.getMenuImage('', name);

    if (isUrl) {
      return Image.network(
        url,
        width: 60,
        height: 60,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => _buildAsset(assetPath, type),
      );
    }
    return _buildAsset(assetPath, type);
  }

  Widget _buildAsset(String path, String type) {
    return Image.asset(
      path,
      width: 60,
      height: 60,
      fit: BoxFit.cover,
      errorBuilder: (_, __, ___) => Container(
        width: 60,
        height: 60,
        color: Colors.grey.shade200,
        child: Icon(type == 'deal' ? Icons.local_offer : Icons.fastfood,
            color: Colors.grey),
      ),
    );
  }

  Widget _buildSummaryRow(
      String label,
      String value, {
        bool isBold = false,
        Color color = Colors.grey,
      }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(
              color: color,
              fontSize: 15,
              fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
            ),
          ),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 15,
              fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
            ),
          ),
        ],
      ),
    );
  }
}
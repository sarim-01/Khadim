import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/screens/checkout/checkout_screen.dart';

class CartScreen extends StatefulWidget {
  const CartScreen({Key? key}) : super(key: key);

  @override
  State<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends State<CartScreen> {
  @override
  void initState() {
    super.initState();
    // On open, pull latest snapshot from server
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<CartProvider>().sync();
    });
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
                            child: _buildItemImage(item.image),
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

  Widget _buildItemImage(String? image) {
    // If backend returns URL later, handle it too
    if (image == null || image.isEmpty) {
      return Container(
        width: 60,
        height: 60,
        color: Colors.grey.shade200,
        child: const Icon(Icons.fastfood),
      );
    }

    final isUrl = image.startsWith('http://') || image.startsWith('https://');

    if (isUrl) {
      return Image.network(
        image,
        width: 60,
        height: 60,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => Container(
          width: 60,
          height: 60,
          color: Colors.grey.shade200,
          child: const Icon(Icons.image_not_supported),
        ),
      );
    }

    return Image.asset(
      image,
      width: 60,
      height: 60,
      fit: BoxFit.cover,
      errorBuilder: (_, __, ___) => Container(
        width: 60,
        height: 60,
        color: Colors.grey.shade200,
        child: const Icon(Icons.image_not_supported),
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
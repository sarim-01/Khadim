import 'package:flutter/material.dart';
import 'package:khaadim/app_config.dart';
import 'package:provider/provider.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/providers/dine_in_provider.dart';
import 'package:khaadim/screens/checkout/checkout_screen.dart';
import 'package:khaadim/screens/dine_in/kiosk_bottom_nav.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/services/dine_in_service.dart';
import 'package:khaadim/utils/ImageResolver.dart';

class CartScreen extends StatefulWidget {
  const CartScreen({super.key});

  @override
  State<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends State<CartScreen> {
  List<Map<String, dynamic>> _recommendations = [];
  final Set<int> _addingRec = {};
  bool _isSendingToKitchen = false;
  String _lastKioskRecommendationKey = '';

  @override
  void initState() {
    super.initState();
    final cartProvider = context.read<CartProvider>();

    // On open, pull latest snapshot from server then load recommendations
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (AppConfig.isKiosk) {
        await _loadKioskRecommendations();
        return;
      }
      await cartProvider.sync();
      _loadRecommendations();
    });
  }

  Future<void> _loadRecommendations() async {
    final cartId = context.read<CartProvider>().cartId;
    if (cartId == null) return;
    final recs = await CartService.fetchRecommendations(cartId: cartId);
    if (mounted) setState(() => _recommendations = recs);
  }

  List<Map<String, dynamic>> _kioskMenuSeedItems(DineInProvider dineIn) {
    final seedItems = <Map<String, dynamic>>[];

    for (final item in dineIn.currentOrderItems) {
      final itemType = (item['item_type'] ?? 'menu_item').toString();
      if (itemType != 'menu_item') {
        continue;
      }

      final rawItemId = item['item_id'];
      final itemId = rawItemId is int
          ? rawItemId
          : int.tryParse(rawItemId.toString()) ?? 0;
      if (itemId <= 0) {
        continue;
      }

      final rawQuantity = item['quantity'];
      final quantity = rawQuantity is int
          ? rawQuantity
          : int.tryParse(rawQuantity.toString()) ?? 1;
      if (quantity <= 0) {
        continue;
      }

      seedItems.add({
        'item_type': 'menu_item',
        'item_id': itemId,
        'quantity': quantity,
      });
    }

    return seedItems;
  }

  String _buildKioskRecommendationKey(List<Map<String, dynamic>> items) {
    final parts = items
        .map((item) => '${item['item_id']}:${item['quantity']}')
        .toList()
      ..sort();
    return parts.join('|');
  }

  void _scheduleKioskRecommendationRefresh(DineInProvider dineIn) {
    final seedItems = _kioskMenuSeedItems(dineIn);
    final key = _buildKioskRecommendationKey(seedItems);

    if (key == _lastKioskRecommendationKey) {
      return;
    }

    _lastKioskRecommendationKey = key;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !AppConfig.isKiosk) {
        return;
      }
      _loadKioskRecommendations();
    });
  }

  Future<void> _loadKioskRecommendations() async {
    final dineIn = context.read<DineInProvider>();
    final sessionId = dineIn.sessionId;

    if (sessionId == null) {
      if (mounted) {
        setState(() => _recommendations = []);
      }
      return;
    }

    final seedItems = _kioskMenuSeedItems(dineIn);
    if (seedItems.isEmpty) {
      if (mounted) {
        setState(() => _recommendations = []);
      }
      return;
    }

    final recs = await DineInService().fetchRecommendations(sessionId, seedItems);

    if (!mounted) return;

    final currentItemIds = seedItems
        .map((item) => item['item_id'])
        .whereType<int>()
        .toSet();

    setState(() {
      _recommendations = recs.where((rec) {
        final rawId = rec['recommended_item_id'];
        final recItemId = rawId is int
            ? rawId
            : int.tryParse(rawId.toString()) ?? 0;
        return recItemId > 0 && !currentItemIds.contains(recItemId);
      }).toList();
    });
  }

  Future<void> _addRecommendedItem(Map<String, dynamic> rec) async {
    if (AppConfig.isKiosk) {
      final dineIn = context.read<DineInProvider>();
      final rawId = rec['recommended_item_id'];
      final itemId =
          rawId is int ? rawId : int.tryParse(rawId.toString()) ?? 0;
      if (itemId <= 0) return;

      final itemName = (rec['recommended_name'] ?? 'Item').toString();
      final rawPrice = rec['recommended_price'];
      final itemPrice = rawPrice is num
          ? rawPrice.toDouble()
          : double.tryParse(rawPrice.toString()) ?? 0;

      setState(() => _addingRec.add(itemId));
      try {
        dineIn.addItem(itemId, 'menu_item', itemName, itemPrice, 1);
        if (mounted) {
          setState(() {
            _recommendations.removeWhere(
              (r) =>
                  ((r['recommended_item_id'] is int
                          ? r['recommended_item_id'] as int
                          : int.tryParse(
                                  (r['recommended_item_id'] ?? '').toString()) ??
                              -1) ==
                      itemId),
            );
          });
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text('$itemName added to cart!'),
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 1),
          ));
        }
        await _loadKioskRecommendations();
      } catch (_) {
        // fail silently
      } finally {
        if (mounted) setState(() => _addingRec.remove(itemId));
      }
      return;
    }

    final cartProvider = context.read<CartProvider>();
    final cartId = cartProvider.cartId;
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
      await cartProvider.sync();
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

  Future<void> _sendToKitchen() async {
    final dineIn = context.read<DineInProvider>();
    if (dineIn.sessionId == null) return;

    setState(() => _isSendingToKitchen = true);

    try {
      final Map<String, Map<String, dynamic>> aggregated =
          <String, Map<String, dynamic>>{};

      void addNormalized(String rawType, int rawId, int rawQuantity) {
        if (rawId <= 0 || rawQuantity <= 0) return;
        final normalizedType = rawType == 'deal' ? 'deal' : 'menu_item';
        final key = '$normalizedType:$rawId';

        final existing = aggregated[key];
        if (existing == null) {
          aggregated[key] = {
            'item_type': normalizedType,
            'item_id': rawId,
            'quantity': rawQuantity,
          };
          return;
        }

        existing['quantity'] = (existing['quantity'] as int) + rawQuantity;
      }

      for (final item in dineIn.currentOrderItems) {
        final itemType = (item['item_type'] ?? 'menu_item').toString();
        final parentQuantity = (item['quantity'] as num?)?.toInt() ??
            int.tryParse((item['quantity'] ?? '1').toString()) ??
            1;

        if (itemType == 'custom_deal') {
          final bundle = item['bundle_items'];
          if (bundle is! List) continue;

          for (final raw in bundle) {
            if (raw is! Map) continue;

            final rawItemType = (raw['item_type'] ?? 'menu_item').toString();
            final rawItemId = raw['item_id'];
            final rawQty = raw['quantity'];

            final resolvedItemId = rawItemId is int
                ? rawItemId
                : int.tryParse(rawItemId.toString()) ?? 0;
            final resolvedQty = rawQty is int
                ? rawQty
                : int.tryParse(rawQty.toString()) ?? 1;

            addNormalized(rawItemType, resolvedItemId, resolvedQty * parentQuantity);
          }

          continue;
        }

        final rawId = item['item_id'];
        final resolvedId =
            rawId is int ? rawId : int.tryParse(rawId.toString()) ?? 0;
        addNormalized(itemType, resolvedId, parentQuantity);
      }

      final items = aggregated.values.toList();

      if (items.isEmpty) {
        throw Exception('No items in current order.');
      }

      await DineInService().placeOrder(dineIn.sessionId!, items);
      dineIn.clearOrder();

      if (!mounted) return;
      showDialog(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Order Sent! 🍽️'),
          content: const Text(
            'Kitchen is preparing your food. You can order more rounds anytime!',
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(context); // close dialog
                Navigator.pop(context); // go back to menu
              },
              child: const Text('Back to Menu'),
            ),
            TextButton(
              onPressed: () {
                Navigator.pop(context);
                Navigator.pushNamed(context, '/kiosk-orders');
              },
              child: const Text('View Orders'),
            ),
          ],
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.toString()),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      if (mounted) setState(() => _isSendingToKitchen = false);
    }
  }

  double _subtotal(List items) {
    return items.fold(0.0, (sum, x) => sum + (x.price * x.quantity));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (AppConfig.isKiosk) {
      final dineIn = context.watch<DineInProvider>();

      return SafeArea(
        child: Scaffold(
          appBar: AppBar(
            title: const Text("Your Cart"),
          ),
          body: _buildKioskBody(theme, dineIn),
          bottomNavigationBar: const KioskBottomNav(currentIndex: 1),
        ),
      );
    }

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
            const deliveryFee = 150.0;
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
                                      .withValues(alpha: 0.3),
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
                        color: Colors.black.withValues(alpha: 0.05),
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
                        onPressed: (cart.isSyncing ||
                                cart.cartId == null ||
                                cart.items.isEmpty)
                            ? null
                            : () {
                                Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (_) => const CheckoutScreen(),
                                  ),
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
                        child: const Text(
                          "Proceed to Checkout",
                          style: TextStyle(fontSize: 16),
                        ),
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

  Widget _buildKioskBody(ThemeData theme, DineInProvider dineIn) {
    _scheduleKioskRecommendationRefresh(dineIn);

    final items = dineIn.currentOrderItems;

    if (items.isEmpty) {
      return const Center(
        child: Text("Your cart is empty", style: TextStyle(fontSize: 16)),
      );
    }

    final subtotal = dineIn.orderTotal;
    final tax = subtotal * 0.05;
    final total = subtotal + tax;

    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: items.length,
            itemBuilder: (_, index) {
              final item = items[index];
              final itemId = (item['item_id'] as num?)?.toInt() ??
                  int.tryParse((item['item_id'] ?? '0').toString()) ??
                  0;
              final itemType = (item['item_type'] ?? 'menu_item').toString();
              final itemName = (item['item_name'] ?? 'Item').toString();
              final itemPrice = (item['price'] as num?)?.toDouble() ??
                  double.tryParse((item['price'] ?? '0').toString()) ??
                  0;
              final quantity = (item['quantity'] as num?)?.toInt() ??
                  int.tryParse((item['quantity'] ?? '1').toString()) ??
                  1;
                final isCustomDeal = itemType == 'custom_deal';

              return Card(
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                margin: const EdgeInsets.only(bottom: 12),
                child: ListTile(
                  leading: ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: _buildItemImage(
                      null,
                      itemName,
                      itemType == 'custom_deal'
                          ? 'custom_deal'
                          : (itemType == 'deal' ? 'deal' : 'item'),
                    ),
                  ),
                  title: Text(
                    itemName,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                  subtitle: Text(
                    "Rs ${itemPrice.toStringAsFixed(2)}",
                    style: const TextStyle(color: Colors.grey),
                  ),
                  trailing: isCustomDeal
                      ? IconButton(
                          icon: const Icon(Icons.delete_outline),
                          color: Colors.orangeAccent,
                          tooltip: 'Remove custom deal',
                          onPressed: () => dineIn.removeItem(itemId, itemType),
                        )
                      : Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            IconButton(
                              icon: const Icon(Icons.remove_circle_outline),
                              color: Colors.orangeAccent,
                              onPressed: () {
                                if (quantity <= 1) {
                                  dineIn.removeItem(itemId, itemType);
                                  return;
                                }

                                dineIn.removeItem(itemId, itemType);
                                dineIn.addItem(
                                  itemId,
                                  itemType,
                                  itemName,
                                  itemPrice,
                                  quantity - 1,
                                );
                              },
                            ),
                            Text(
                              quantity.toString(),
                              style: const TextStyle(fontSize: 16),
                            ),
                            IconButton(
                              icon: const Icon(Icons.add_circle_outline),
                              color: Colors.orangeAccent,
                              onPressed: () {
                                dineIn.addItem(
                                  itemId,
                                  itemType,
                                  itemName,
                                  itemPrice,
                                  1,
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
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  itemCount: _recommendations.length,
                  itemBuilder: (_, i) {
                    final rec = _recommendations[i];
                    final rawId = rec['recommended_item_id'];
                    final itemId = rawId is int
                        ? rawId
                        : int.tryParse(rawId.toString()) ?? 0;
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
                              .withValues(alpha: 0.3),
                        ),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            (rec['recommended_name'] ?? '').toString(),
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
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                "Rs ${((rec['recommended_price'] as num?) ?? 0).toStringAsFixed(0)}",
                                style: const TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.bold,
                                  color: Color(0xFFD4AF37),
                                ),
                              ),
                              GestureDetector(
                                onTap: isAdding
                                    ? null
                                    : () => _addRecommendedItem(rec),
                                child: AnimatedContainer(
                                  duration: const Duration(milliseconds: 200),
                                  width: 28,
                                  height: 28,
                                  decoration: BoxDecoration(
                                    color: isAdding
                                        ? const Color(0xFF2A2A2A)
                                        : const Color(0xFFD4AF37),
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: isAdding
                                      ? const Padding(
                                          padding: EdgeInsets.all(6),
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            color: Color(0xFFD4AF37),
                                          ),
                                        )
                                      : const Icon(Icons.add,
                                          color: Colors.black, size: 18),
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
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.05),
                blurRadius: 6,
                offset: const Offset(0, -3),
              ),
            ],
          ),
          child: Column(
            children: [
              _buildSummaryRow("Subtotal", "Rs ${subtotal.toStringAsFixed(2)}"),
              _buildSummaryRow("Tax", "Rs ${tax.toStringAsFixed(2)}"),
              const Divider(),
              _buildSummaryRow(
                "Total",
                "Rs ${total.toStringAsFixed(2)}",
                isBold: true,
                color: theme.colorScheme.onSurface,
              ),
              const SizedBox(height: 10),
              ElevatedButton(
                onPressed: _isSendingToKitchen || items.isEmpty
                    ? null
                    : _sendToKitchen,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orangeAccent,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                child: _isSendingToKitchen
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Text(
                        "Send to Kitchen",
                        style: TextStyle(fontSize: 16),
                      ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildItemImage(String? image, String name, String type) {
    final url = (image ?? '').trim();
    final isUrl = url.startsWith('http://') || url.startsWith('https://');

    final assetPath = type == 'custom_deal'
      ? 'assets/images/deals/custom_deal.png'
      : (type == 'deal'
        ? ImageResolver.getDealImage(name)
        : ImageResolver.getMenuImage('', name));

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
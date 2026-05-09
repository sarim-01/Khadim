import 'package:flutter/material.dart';
import 'package:khaadim/services/api_config.dart';
import 'package:khaadim/services/favorites_service.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/utils/ImageResolver.dart';

class FavoritesScreen extends StatefulWidget {
  const FavoritesScreen({super.key});

  @override
  State<FavoritesScreen> createState() => _FavoritesScreenState();
}

class _FavoritesScreenState extends State<FavoritesScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  bool _loading = true;
  String? _error;

  List<Map<String, dynamic>> _items = [];
  List<Map<String, dynamic>> _deals = [];
  List<Map<String, dynamic>> _customDeals = [];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _loadFavourites();
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _loadFavourites() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await FavouritesService.getFavourites();
      if (mounted) {
        setState(() {
          _items = List<Map<String, dynamic>>.from(data['items'] ?? []);
          _deals = List<Map<String, dynamic>>.from(data['deals'] ?? []);
          _customDeals =
              List<Map<String, dynamic>>.from(data['custom_deals'] ?? []);
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString().replaceFirst('ApiException: ', '').replaceFirst('Exception: ', '');
          _loading = false;
        });
      }
    }
  }

  Future<void> _toggleAndRemove({
    int? itemId,
    int? dealId,
    int? customDealId,
  }) async {
    try {
      await FavouritesService.toggleFavourite(
        itemId: itemId,
        dealId: dealId,
        customDealId: customDealId,
      );
      await _loadFavourites();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Removed from favourites'),
          behavior: SnackBarBehavior.floating,
          duration: Duration(seconds: 1),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(e.toString()),
        behavior: SnackBarBehavior.floating,
      ));
    }
  }

  // ── Quick-order helper ───────────────────────────────────────
  Future<void> _quickOrder(String itemType, int itemId, String name) async {
    try {
      // Get or create active cart
      final cartRes = await CartService.getOrCreateActiveCart();
      final cartId = cartRes['cart_id']?.toString() ?? '';
      await CartService.addItem(
        cartId: cartId,
        itemType: itemType,
        itemId: itemId,
        quantity: 1,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('$name added to cart!'),
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 1),
      ));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(e.toString()),
        behavior: SnackBarBehavior.floating,
      ));
    }
  }

  // ── Image helper ─────────────────────────────────────────────
  Widget _itemImage(String? imageUrl, String name, String type, {double size = 60}) {
    final url = (imageUrl ?? '').trim();
    final bundled = ApiConfig.flutterBundledAssetPath(url);
    if (bundled != null) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Image.asset(
          bundled,
          width: size,
          height: size,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) =>
              _assetImage(name, type, size: size),
        ),
      );
    }
    final hasUrl = url.startsWith('http://') || url.startsWith('https://');
    final networkUrl = ApiConfig.resolvePublicImageUrl(url);
    if (networkUrl != null) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Image.network(networkUrl,
            width: size, height: size, fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => _assetImage(name, type, size: size)),
      );
    }
    if (hasUrl) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Image.network(url,
            width: size, height: size, fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => _assetImage(name, type, size: size)),
      );
    }
    return _assetImage(name, type, size: size);
  }

  Widget _assetImage(String name, String type, {double size = 60}) {
    // Determine the correct local asset path based on type
    final String fallback = type == 'deal'
        ? ImageResolver.getDealImage(name)
        : ImageResolver.getMenuImage('', name);

    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: Image.asset(fallback,
          width: size, height: size, fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => Container(
                width: size, height: size,
                decoration: BoxDecoration(
                    color: Colors.grey[200],
                    borderRadius: BorderRadius.circular(8)),
                child: Icon(type == 'deal' ? Icons.local_offer : Icons.fastfood,
                    color: Colors.grey),
              )),
    );
  }

  // ── Empty state ──────────────────────────────────────────────
  Widget _emptyState(String label) => Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.favorite_border, size: 60, color: Colors.grey),
            const SizedBox(height: 12),
            Text('No favourite $label yet',
                style: const TextStyle(
                    fontSize: 16, fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            Text('Tap ♥ on any $label to save it here',
                style: const TextStyle(color: Colors.grey)),
          ],
        ),
      );

  // ── Item card ────────────────────────────────────────────────
  Widget _itemCard(Map<String, dynamic> f, ThemeData theme) {
    final name = f['item_name']?.toString() ?? 'Item';
    final price = (f['price'] as num?)?.toDouble() ?? 0.0;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(children: [
          _itemImage(f['image_url']?.toString(), name, 'item'),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(name,
                  style: const TextStyle(
                      fontWeight: FontWeight.bold, fontSize: 15)),
              const SizedBox(height: 4),
              Text('Rs ${price.toStringAsFixed(0)}',
                  style: TextStyle(
                      color: theme.colorScheme.primary,
                      fontWeight: FontWeight.w600)),
            ]),
          ),
          Column(children: [
            IconButton(
              icon: const Icon(Icons.favorite, color: Colors.redAccent),
              onPressed: () =>
                  _toggleAndRemove(itemId: f['item_id'] as int?),
              tooltip: 'Remove',
            ),
            ElevatedButton(
              onPressed: () =>
                  _quickOrder('menu_item', f['item_id'] as int, name),
              style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orangeAccent,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  textStyle: const TextStyle(fontSize: 12)),
              child: const Text('Order'),
            ),
          ]),
        ]),
      ),
    );
  }

  // ── Deal card ────────────────────────────────────────────────
  Widget _dealCard(Map<String, dynamic> f, ThemeData theme) {
    final name = f['deal_name']?.toString() ?? 'Deal';
    final price = (f['price'] as num?)?.toDouble() ?? 0.0;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(children: [
          _itemImage(f['image_url']?.toString(), name, 'deal'),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(name,
                  style: const TextStyle(
                      fontWeight: FontWeight.bold, fontSize: 15)),
              const SizedBox(height: 4),
              Text('Rs ${price.toStringAsFixed(0)}',
                  style: TextStyle(
                      color: theme.colorScheme.primary,
                      fontWeight: FontWeight.w600)),
            ]),
          ),
          Column(children: [
            IconButton(
              icon: const Icon(Icons.favorite, color: Colors.redAccent),
              onPressed: () =>
                  _toggleAndRemove(dealId: f['deal_id'] as int?),
              tooltip: 'Remove',
            ),
            ElevatedButton(
              onPressed: () =>
                  _quickOrder('deal', f['deal_id'] as int, name),
              style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orangeAccent,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  textStyle: const TextStyle(fontSize: 12)),
              child: const Text('Order'),
            ),
          ]),
        ]),
      ),
    );
  }

  // ── Custom deal card ─────────────────────────────────────────
  Widget _customDealCard(Map<String, dynamic> f, ThemeData theme) {
    final cdId = f['custom_deal_id'] as int?;
    final total = (f['total_price'] as num?)?.toDouble() ?? 0.0;
    final discount = (f['discount_amount'] as num?)?.toDouble() ?? 0.0;
    final groupSize = (f['group_size'] as num?)?.toInt() ?? 1;
    final items = List<Map<String, dynamic>>.from(f['items'] ?? []);

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.star_rounded, color: Colors.orangeAccent, size: 20),
            const SizedBox(width: 6),
            Expanded(
              child: Text('Custom Deal #$cdId (${groupSize}p)',
                  style: const TextStyle(
                      fontWeight: FontWeight.bold, fontSize: 15)),
            ),
            IconButton(
              icon: const Icon(Icons.favorite, color: Colors.redAccent),
              onPressed: () => _toggleAndRemove(customDealId: cdId),
              tooltip: 'Remove',
            ),
          ]),
          if (items.isNotEmpty) ...[
            const SizedBox(height: 6),
            ...items.map((it) => Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Text(
                    '• ${it['item_name']} ×${it['quantity']}',
                    style: const TextStyle(fontSize: 13),
                  ),
                )),
          ],
          const SizedBox(height: 8),
          Row(children: [
            Text('Rs ${total.toStringAsFixed(0)}',
                style: TextStyle(
                    color: theme.colorScheme.primary,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
            if (discount > 0) ...[
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                    color: Colors.green.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(6)),
                child: Text('Save Rs ${discount.toStringAsFixed(0)}',
                    style: const TextStyle(
                        color: Colors.green, fontSize: 11, fontWeight: FontWeight.w600)),
              ),
            ],
            const Spacer(),
            ElevatedButton(
              onPressed: cdId != null
                  ? () => _quickOrder('custom_deal', cdId, 'Custom Deal #$cdId')
                  : null,
              style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orangeAccent,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  textStyle: const TextStyle(fontSize: 12)),
              child: const Text('Order'),
            ),
          ]),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Favourites'),
        actions: [
          IconButton(
            onPressed: _loading ? null : _loadFavourites,
            icon: const Icon(Icons.refresh),
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          tabs: [
            Tab(text: 'Items (${_items.length})'),
            Tab(text: 'Deals (${_deals.length})'),
            Tab(text: 'Custom (${_customDeals.length})'),
          ],
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.error_outline,
                            size: 48, color: Colors.grey),
                        const SizedBox(height: 12),
                        Text(_error!, textAlign: TextAlign.center),
                        const SizedBox(height: 16),
                        ElevatedButton(
                          onPressed: _loadFavourites,
                          child: const Text('Retry'),
                        ),
                      ],
                    ),
                  ),
                )
              : TabBarView(
                  controller: _tabController,
                  children: [
                    // Items tab
                    _items.isEmpty
                        ? _emptyState('items')
                        : ListView.builder(
                            padding: const EdgeInsets.all(16),
                            itemCount: _items.length,
                            itemBuilder: (_, i) =>
                                _itemCard(_items[i], theme),
                          ),
                    // Deals tab
                    _deals.isEmpty
                        ? _emptyState('deals')
                        : ListView.builder(
                            padding: const EdgeInsets.all(16),
                            itemCount: _deals.length,
                            itemBuilder: (_, i) =>
                                _dealCard(_deals[i], theme),
                          ),
                    // Custom deals tab
                    _customDeals.isEmpty
                        ? _emptyState('custom deals')
                        : ListView.builder(
                            padding: const EdgeInsets.all(16),
                            itemCount: _customDeals.length,
                            itemBuilder: (_, i) =>
                                _customDealCard(_customDeals[i], theme),
                          ),
                  ],
                ),
    );
  }
}
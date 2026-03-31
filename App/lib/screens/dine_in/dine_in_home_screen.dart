import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:khaadim/providers/dine_in_provider.dart';
import 'package:khaadim/screens/chat/chat_bottom_sheet.dart';
import 'package:khaadim/screens/discover/custom_deal_screen.dart';
import 'package:khaadim/screens/dine_in/kiosk_bottom_nav.dart';
import 'package:khaadim/services/api_config.dart';
import 'package:khaadim/utils/ImageResolver.dart';
import 'package:provider/provider.dart';

class DineInHomeScreen extends StatefulWidget {
  const DineInHomeScreen({super.key});

  @override
  State<DineInHomeScreen> createState() => _DineInHomeScreenState();
}

class _DineInHomeScreenState extends State<DineInHomeScreen> {
  bool _isLoadingTopSellers = true;
  String? _topSellersError;
  List<Map<String, dynamic>> _topMenuItems = [];
  List<Map<String, dynamic>> _topDeals = [];

  static const Map<String, String> _categoryFallbackImages = {
    'bbq': 'assets/images/menu/bbq/chicken_tikka.jpeg',
    'bread': 'assets/images/menu/bread/roti.jpeg',
    'chinese': 'assets/images/menu/chinese/kung pao chicken.png',
    'desi': 'assets/images/menu/desi/chicken_karahi.jpeg',
    'drinks': 'assets/images/menu/drinks/cola.jpg',
    'fast_food': 'assets/images/menu/fast_food/cheeseburger.png',
  };

  @override
  void initState() {
    super.initState();
    _loadTopSellers();
  }

  Future<void> _loadTopSellers() async {
    setState(() {
      _isLoadingTopSellers = true;
      _topSellersError = null;
    });

    try {
      final token = Provider.of<DineInProvider>(context, listen: false).token;
      final response = await http.get(
        Uri.parse(
          '${ApiConfig.baseUrl}/dine-in/top-sellers?ts=${DateTime.now().millisecondsSinceEpoch}',
        ),
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache',
          'Pragma': 'no-cache',
          if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        },
      ).timeout(const Duration(seconds: 8));

      final dynamic decoded =
          response.body.isNotEmpty ? jsonDecode(response.body) : <String, dynamic>{};

      if (response.statusCode < 200 || response.statusCode >= 300) {
        String message = 'Failed to load top sellers';
        if (decoded is Map<String, dynamic> && decoded['detail'] != null) {
          message = decoded['detail'].toString();
        }
        throw Exception(message);
      }

      final List<dynamic> rawItems;
      final List<dynamic> rawMenuItems;
      final List<dynamic> rawDeals;
      if (decoded is List) {
        rawItems = decoded;
        rawMenuItems = rawItems
            .where((e) =>
                e is Map &&
                ((e['item_type'] ?? '').toString().toLowerCase() != 'deal'))
            .toList();
        rawDeals = rawItems
            .where((e) =>
                e is Map && ((e['item_type'] ?? '').toString().toLowerCase() == 'deal'))
            .toList();
      } else if (decoded is Map<String, dynamic>) {
        final maybeItems = decoded['top_sellers'] ?? decoded['items'] ?? decoded['data'];
        rawItems = maybeItems is List ? maybeItems : <dynamic>[];
        final maybeMenuItems = decoded['top_menu_items'];
        rawMenuItems = maybeMenuItems is List
            ? maybeMenuItems
            : rawItems
                .where((e) =>
                    e is Map &&
                    ((e['item_type'] ?? '').toString().toLowerCase() != 'deal'))
                .toList();
        final maybeDeals = decoded['top_deals'];
        rawDeals = maybeDeals is List
            ? maybeDeals
            : rawItems
                .where((e) =>
                    e is Map && ((e['item_type'] ?? '').toString().toLowerCase() == 'deal'))
                .toList();
      } else {
        rawItems = <dynamic>[];
        rawMenuItems = <dynamic>[];
        rawDeals = <dynamic>[];
      }

      final menuItems = rawMenuItems
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();

      final deals = rawDeals
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();

      if (!mounted) return;
      setState(() {
        _topMenuItems = menuItems;
        _topDeals = deals;
        _isLoadingTopSellers = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoadingTopSellers = false;
        _topSellersError = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  Future<void> _handleRefresh() async {
    await _loadTopSellers();
  }

  void _addTopSellerItem(Map<String, dynamic> item) {
    final itemId = _resolveItemId(item);
    final itemType = _resolveItemType(item);
    final name = (item['item_name'] ?? item['name'] ?? 'Item').toString();
    final rawPrice = item['item_price'] ?? item['price'] ?? 0;
    final price = rawPrice is num
        ? rawPrice.toDouble()
        : double.tryParse(rawPrice.toString()) ?? 0.0;

    Provider.of<DineInProvider>(context, listen: false).addItem(
      itemId,
      itemType,
      name,
      price,
      1,
    );

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('$name added'),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  List<String> _extractDealItems(Map<String, dynamic> item) {
    final rawItems = item['deal_items'] ?? item['items'] ?? item['deal_item_names'];

    if (rawItems is List) {
      return rawItems
          .map((entry) {
            if (entry is Map) {
              final name = entry['item_name'] ?? entry['name'] ?? entry['title'];
              return name?.toString().trim() ?? '';
            }
            return entry.toString().trim();
          })
          .where((name) => name.isNotEmpty)
          .toList();
    }

    final text = rawItems?.toString().trim() ?? '';
    if (text.isEmpty) {
      return const <String>[];
    }

    return text
        .split(RegExp(r',|\||\n'))
        .map((entry) => entry.trim())
        .where((entry) => entry.isNotEmpty)
        .toList();
  }

  void _showDealItemsToast(Map<String, dynamic> item) {
    final theme = Theme.of(context);
    final name = (item['item_name'] ?? item['name'] ?? 'Deal').toString();
    final itemNames = _extractDealItems(item);

    showGeneralDialog<void>(
      context: context,
      barrierDismissible: true,
      barrierLabel: 'Close deal details',
      barrierColor: Colors.black.withValues(alpha: 0.45),
      transitionDuration: const Duration(milliseconds: 180),
      pageBuilder: (_, __, ___) {
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => Navigator.of(context).pop(),
          child: SafeArea(
            child: Center(
              child: GestureDetector(
                onTap: () {},
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 420, maxHeight: 500),
                  child: Material(
                    color: theme.colorScheme.surface,
                    elevation: 12,
                    borderRadius: BorderRadius.circular(20),
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  name,
                                  style: theme.textTheme.titleMedium?.copyWith(
                                    fontWeight: FontWeight.w700,
                                  ),
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              IconButton(
                                onPressed: () => Navigator.of(context).pop(),
                                icon: const Icon(Icons.close_rounded),
                              ),
                            ],
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'Items in this deal',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
                            ),
                          ),
                          const SizedBox(height: 12),
                          Flexible(
                            child: itemNames.isEmpty
                                ? Container(
                                    width: double.infinity,
                                    padding: const EdgeInsets.all(12),
                                    decoration: BoxDecoration(
                                      color: theme.colorScheme.surfaceContainerHighest,
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: Text(
                                      'Deal items details coming soon.',
                                      style: theme.textTheme.bodyMedium,
                                    ),
                                  )
                                : SingleChildScrollView(
                                    child: Column(
                                      children: [
                                        for (final itemName in itemNames)
                                          Container(
                                            width: double.infinity,
                                            margin: const EdgeInsets.only(bottom: 8),
                                            padding: const EdgeInsets.symmetric(
                                              horizontal: 12,
                                              vertical: 10,
                                            ),
                                            decoration: BoxDecoration(
                                              color: theme.colorScheme.surfaceContainerHighest,
                                              borderRadius: BorderRadius.circular(10),
                                            ),
                                            child: Row(
                                              children: [
                                                Icon(
                                                  Icons.check_circle_rounded,
                                                  size: 18,
                                                  color: theme.colorScheme.primary,
                                                ),
                                                const SizedBox(width: 10),
                                                Expanded(
                                                  child: Text(
                                                    itemName,
                                                    style: theme.textTheme.bodyMedium,
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                      ],
                                    ),
                                  ),
                          ),
                          const SizedBox(height: 10),
                          Row(
                            children: [
                              Expanded(
                                child: OutlinedButton(
                                  onPressed: () => Navigator.of(context).pop(),
                                  child: const Text('Close'),
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: ElevatedButton(
                                  onPressed: () {
                                    Navigator.of(context).pop();
                                    _addTopSellerItem(item);
                                  },
                                  child: const Text('Add Deal'),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
      },
      transitionBuilder: (context, animation, _, child) {
        final curved = CurvedAnimation(parent: animation, curve: Curves.easeOutCubic);
        return FadeTransition(
          opacity: curved,
          child: ScaleTransition(
            scale: Tween<double>(begin: 0.96, end: 1.0).animate(curved),
            child: child,
          ),
        );
      },
    );
  }

  int _resolveItemId(Map<String, dynamic> item) {
    final raw = item['item_id'] ?? item['id'] ?? 0;
    if (raw is num) return raw.toInt();
    return int.tryParse(raw.toString()) ?? 0;
  }

  String _resolveItemType(Map<String, dynamic> item) {
    final type = (item['item_type'] ?? 'menu_item').toString().trim().toLowerCase();
    return type == 'deal' ? 'deal' : 'menu_item';
  }

  String _resolveImagePath(Map<String, dynamic> item) {
    final imageUrl = (item['image_url'] ?? '').toString().trim();
    if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
      return imageUrl;
    }
    if (imageUrl.startsWith('/') && !imageUrl.startsWith('/assets/')) {
      return '${ApiConfig.baseUrl}$imageUrl';
    }

    // For local or malformed asset paths, prefer known good bundled assets.
    return _resolveLocalFallbackImage(item);
  }

  String _resolveLocalFallbackImage(Map<String, dynamic> item) {
    final itemType = _resolveItemType(item);
    final name = (item['item_name'] ?? item['name'] ?? 'Item').toString();

    if (itemType == 'deal') {
      return ImageResolver.getDealImage(name);
    }

    final category = (item['item_category'] ?? 'fast_food').toString();
    final resolved = ImageResolver.getMenuImage(category, name);
    if (resolved == ImageResolver.fallbackImage &&
        _categoryFallbackImages.containsKey(category.toLowerCase())) {
      return _categoryFallbackImages[category.toLowerCase()]!;
    }
    return resolved;
  }

  Widget _assetImageWithFallback(String path, {double size = 64}) {
    return Image.asset(
      path,
      width: size,
      height: size,
      fit: BoxFit.cover,
      errorBuilder: (_, __, ___) => Image.asset(
        ImageResolver.fallbackImage,
        width: size,
        height: size,
        fit: BoxFit.cover,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final tableNumber =
        Provider.of<DineInProvider>(context).tableNumber?.trim().isNotEmpty == true
            ? Provider.of<DineInProvider>(context).tableNumber!.trim()
            : '--';

    return SafeArea(
      child: Scaffold(
        appBar: AppBar(
          title: Text(
            'Table $tableNumber',
            style: theme.textTheme.bodyLarge?.copyWith(
              fontWeight: FontWeight.w600,
            ),
          ),
          actions: [
            IconButton(
              icon: const Icon(Icons.shopping_cart_outlined),
              onPressed: () {
                Navigator.pushNamed(context, '/kiosk-cart');
              },
            ),
          ],
        ),
        body: RefreshIndicator(
          onRefresh: _handleRefresh,
          color: theme.colorScheme.primary,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _buildCustomDealCard(context),
              const SizedBox(height: 20),
              _buildTopSellersSection(context),
            ],
          ),
        ),
        bottomNavigationBar: const KioskBottomNav(currentIndex: 0),
        floatingActionButton: FloatingActionButton(
          backgroundColor: theme.colorScheme.primary,
          foregroundColor: Colors.black,
          heroTag: 'kioskVoiceButton',
          child: const Icon(Icons.mic_none_rounded),
          onPressed: () {
            showModalBottomSheet(
              context: context,
              isScrollControlled: true,
              backgroundColor: Colors.transparent,
              builder: (context) {
                return DraggableScrollableSheet(
                  initialChildSize: 0.65,
                  minChildSize: 0.4,
                  maxChildSize: 0.95,
                  expand: false,
                  builder: (_, controller) {
                    return ChatBottomSheet(
                      mode: 'voice',
                      scrollController: controller,
                    );
                  },
                );
              },
            );
          },
        ),
      ),
    );
  }

  Widget _buildTopSellersSection(BuildContext context) {
    final theme = Theme.of(context);
    final hasItems = _topMenuItems.isNotEmpty || _topDeals.isNotEmpty;

    if (_isLoadingTopSellers) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 28),
        child: Center(child: CircularProgressIndicator()),
      );
    }

    if (_topSellersError != null) {
      return Container(
        margin: const EdgeInsets.only(bottom: 20),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: theme.colorScheme.surface,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(_topSellersError!, style: theme.textTheme.bodyMedium),
            const SizedBox(height: 8),
            TextButton.icon(
              onPressed: _loadTopSellers,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        
        const SizedBox(height: 12),
        if (!hasItems)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text(
              'No popular items yet.',
              style: theme.textTheme.bodyMedium,
            ),
          )
        else ...[
          _buildSellerGroup(
            context,
            title: 'Top Menu Items',
            icon: Icons.restaurant_menu,
            accent: theme.colorScheme.primary,
            items: _topMenuItems,
          ),
          if (_topMenuItems.isNotEmpty && _topDeals.isNotEmpty)
            const SizedBox(height: 12),
          _buildSellerGroup(
            context,
            title: 'Top Deals',
            icon: Icons.local_offer,
            accent: Colors.orangeAccent,
            items: _topDeals,
          ),
        ],
        const SizedBox(height: 12),
      ],
    );
  }

  Widget _buildSellerGroup(
    BuildContext context, {
    required String title,
    required IconData icon,
    required Color accent,
    required List<Map<String, dynamic>> items,
  }) {
    final theme = Theme.of(context);

    if (items.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: accent.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: accent, size: 18),
              const SizedBox(width: 6),
              Text(
                title,
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ListView.separated(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: items.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (_, index) => _buildTopSellerCard(context, items[index]),
          ),
        ],
      ),
    );
  }

  Widget _buildTopSellerCard(BuildContext context, Map<String, dynamic> item) {
    final theme = Theme.of(context);
    final itemType = _resolveItemType(item);
    final isDeal = itemType == 'deal';
    final name = (item['item_name'] ?? item['name'] ?? 'Item').toString();
    final rawPrice = item['item_price'] ?? item['price'] ?? 0;
    final price = rawPrice is num
        ? rawPrice.toDouble()
        : double.tryParse(rawPrice.toString()) ?? 0.0;
    final soldCount = (item['sold_count'] as num?)?.toInt() ?? 0;
    final imagePath = _resolveImagePath(item);
    final isNetworkImage = imagePath.startsWith('http://') || imagePath.startsWith('https://');

    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: isDeal ? () => _showDealItemsToast(item) : null,
        child: Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
              color: isDeal
                  ? Colors.orangeAccent.withValues(alpha: 0.45)
                  : theme.colorScheme.outline.withValues(alpha: 0.15),
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.04),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: isNetworkImage
                    ? Image.network(
                        imagePath,
                        width: 64,
                        height: 64,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => _assetImageWithFallback(
                          _resolveLocalFallbackImage(item),
                        ),
                      )
                    : _assetImageWithFallback(imagePath),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      name,
                      style: theme.textTheme.bodyLarge?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Rs ${price.toStringAsFixed(0)}',
                      style: theme.textTheme.titleSmall?.copyWith(
                        color: theme.colorScheme.primary,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    if (soldCount > 0)
                      Text(
                        '$soldCount sold',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              ElevatedButton(
                onPressed: () => _addTopSellerItem(item),
                style: ElevatedButton.styleFrom(
                  backgroundColor:
                      isDeal ? Colors.orangeAccent : theme.colorScheme.primary,
                  foregroundColor: Colors.white,
                  elevation: 0,
                  minimumSize: const Size(68, 32),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  visualDensity: VisualDensity.compact,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
                child: const Text('Add'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCustomDealCard(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return GestureDetector(
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const CustomDealScreen()),
        );
      },
      child: Container(
        width: double.infinity,
        decoration: BoxDecoration(
          color: isDark ? const Color(0xFF1E1E1E) : const Color(0xFF1A1A2E),
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.25),
              blurRadius: 14,
              offset: const Offset(0, 6),
            ),
          ],
        ),
        child: Stack(
          children: [
            // Subtle accent circle decoration
            Positioned(
              right: -20,
              top: -20,
              child: Container(
                width: 100,
                height: 100,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: theme.colorScheme.primary.withOpacity(0.08),
                ),
              ),
            ),
            Positioned(
              right: 16,
              bottom: -12,
              child: Container(
                width: 60,
                height: 60,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: theme.colorScheme.primary.withOpacity(0.05),
                ),
              ),
            ),
            // Content
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // AI chip label
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 10,
                            vertical: 4,
                          ),
                          decoration: BoxDecoration(
                            color: theme.colorScheme.primary.withOpacity(0.15),
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(
                              color: theme.colorScheme.primary.withOpacity(0.3),
                              width: 1,
                            ),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.auto_awesome,
                                color: theme.colorScheme.primary,
                                size: 12,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                'AI-Powered',
                                style: TextStyle(
                                  color: theme.colorScheme.primary,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                  letterSpacing: 0.4,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 10),
                        const Text(
                          'Create Your\nCustom Deal',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            height: 1.25,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'Tell the AI what you\'re craving and get a deal built just for you.',
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.55),
                            fontSize: 12,
                            height: 1.4,
                          ),
                        ),
                        const SizedBox(height: 14),
                        // CTA button
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 8,
                          ),
                          decoration: BoxDecoration(
                            color: theme.colorScheme.primary,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                'Try Now',
                                style: TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w600,
                                  fontSize: 13,
                                ),
                              ),
                              SizedBox(width: 6),
                              Icon(
                                Icons.arrow_forward_rounded,
                                color: Colors.white,
                                size: 15,
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Right icon
                  Container(
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary.withOpacity(0.12),
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      Icons.restaurant_menu_rounded,
                      color: theme.colorScheme.primary,
                      size: 28,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

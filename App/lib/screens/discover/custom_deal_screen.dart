import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app_config.dart';
import '../../models/custom_deal_model.dart';
import '../../providers/cart_provider.dart';
import '../../providers/dine_in_provider.dart';
import '../../services/cart_service.dart';
import '../../services/deal_service.dart';

class CustomDealScreen extends StatefulWidget {
  const CustomDealScreen({super.key});

  @override
  State<CustomDealScreen> createState() => _CustomDealScreenState();
}

class _CustomDealScreenState extends State<CustomDealScreen> {
  final TextEditingController _keywordsController = TextEditingController();

  int _personCount = 1;
  bool _isLoading = false;
  CustomDealResponse? _dealResponse;
  String? _error;

  final List<String> _allSuggestions = <String>[
    'Burger deal for 2',
    'BBQ combo for 3',
    'Pakistani meal for 4',
    'Chinese combo for 2',
    'Fast food deal for 2',
    'Biryani deal for 3',
    'Desi dinner for 5',
    'Zinger combo for 2',
    'Pizza deal for 4',
    'Family BBQ platter for 4',
  ];

  @override
  void dispose() {
    _keywordsController.dispose();
    super.dispose();
  }

  int? _extractPersonCount(String text) {
    final RegExpMatch? match = RegExp(r'\b(\d+)\b').firstMatch(text);
    if (match == null) return null;
    return int.tryParse(match.group(1)!);
  }

  bool _looksLikeFullRequest(String input) {
    final String lower = input.toLowerCase();

    return lower.contains('deal') ||
        lower.contains('for ') ||
        lower.contains('burger') ||
        lower.contains('biryani') ||
        lower.contains('bbq') ||
        lower.contains('pizza') ||
        lower.contains('desi') ||
        lower.contains('fast food') ||
        lower.contains('chinese') ||
        lower.contains('pakistani') ||
        lower.contains('combo') ||
        lower.contains('meal');
  }

  String _normalizeQuery(String rawInput) {
    final String cleaned = rawInput.trim().replaceAll(RegExp(r'\s+'), ' ');

    if (_looksLikeFullRequest(cleaned)) {
      return cleaned;
    }

    return 'Make a deal for $_personCount person${_personCount > 1 ? 's' : ''} with $cleaned';
  }

  String _friendlyError(Object error) {
    final String text = error.toString();

    if (text.contains('Exception:')) {
      return text.replaceFirst('Exception:', '').trim();
    }

    if (text.toLowerCase().contains('failed to fetch') ||
        text.toLowerCase().contains('socket') ||
        text.toLowerCase().contains('connection')) {
      return 'Could not connect to server. Please try again.';
    }

    if (text.toLowerCase().contains('500')) {
      return 'Server error while creating deal. Please try a different request.';
    }

    return text;
  }

  Future<void> _createDeal() async {
    FocusScope.of(context).unfocus();

    final String rawInput = _keywordsController.text.trim();

    if (rawInput.isEmpty) {
      setState(() {
        _error = 'Please enter what kind of deal you want.';
        _dealResponse = null;
      });

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please enter what kind of deal you want.'),
        ),
      );
      return;
    }

    final String query = _normalizeQuery(rawInput);

    setState(() {
      _isLoading = true;
      _error = null;
      _dealResponse = null;
    });

    try {
      final Map<String, dynamic> response =
      await DealService.createCustomDeal(query);
      final CustomDealResponse deal = CustomDealResponse.fromJson(response);

      if (!mounted) return;

      setState(() {
        _dealResponse = deal;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        _error = _friendlyError(e);
        _isLoading = false;
      });
    }
  }

  Future<void> _addToCart() async {
    if (_dealResponse == null || !_dealResponse!.hasItems) return;

    if (AppConfig.isKiosk) {
      final DineInProvider dineInProvider =
          Provider.of<DineInProvider>(context, listen: false);

      if (dineInProvider.sessionId == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Session not available. Please login again.')),
        );
        return;
      }

      final int localCustomDealId = DateTime.now().microsecondsSinceEpoch;
      final String title =
          'Custom Deal (for $_personCount ${_personCount == 1 ? 'person' : 'people'})';

      dineInProvider.addCustomDeal(
        customDealId: localCustomDealId,
        title: title,
        totalPrice: _dealResponse!.totalPrice,
        groupSize: _personCount,
        bundleItems: _dealResponse!.items
            .map((CustomDealItem item) => {
                  'item_id': item.itemId,
                  'item_type': item.itemType == 'deal' ? 'deal' : 'menu_item',
                  'item_name': item.itemName,
                  'price': item.price,
                  'quantity': item.quantity,
                })
            .toList(),
      );

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Custom deal added to cart'),
          backgroundColor: Colors.green,
        ),
      );
      Navigator.pop(context);
      return;
    }

    final CartProvider cartProvider =
        Provider.of<CartProvider>(context, listen: false);
    final String? cartId = cartProvider.cartId;

    if (cartId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Cart not available')),
      );
      return;
    }

    setState(() => _isLoading = true);

    try {
      // Step 1: Persist the deal bundle and get a single custom_deal_id
      final double standardPrice = _dealResponse!.items.fold(
        0.0,
        (sum, item) => sum + (item.price * item.quantity),
      );
      final double discountAmount =
          (standardPrice - _dealResponse!.totalPrice).clamp(0.0, standardPrice);

      final Map<String, dynamic> saveResult = await CartService.saveCustomDeal(
        groupSize: _personCount,
        totalPrice: _dealResponse!.totalPrice,
        discountAmount: discountAmount,
        items: _dealResponse!.items
            .map((CustomDealItem item) => {
                  'item_id': item.itemId,
                  'item_name': item.itemName,
                  'quantity': item.quantity,
                  'unit_price': item.price,
                })
            .toList(),
      );

      final int? customDealId =
          saveResult['custom_deal_id'] as int?;
      if (customDealId == null) {
        throw Exception('Server did not return a custom_deal_id');
      }

      // Step 2: Add ONE locked row to cart — item_type = 'custom_deal'
      await CartService.addItem(
        cartId: cartId,
        itemType: 'custom_deal',
        itemId: customDealId,
        quantity: 1,
      );

      // Step 3: Sync provider so cart badge and screen update
      await cartProvider.sync();

      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Custom deal added to cart'),
          backgroundColor: Colors.green,
        ),
      );

      Navigator.pop(context);
    } catch (e) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: ${_friendlyError(e)}')),
      );
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }


  String _cleanMessage(String msg) {
    return msg
        .replaceAll(RegExp(r'\*\*'), '')
        .replaceAll(RegExp(r'[\u{1F000}-\u{1FFFF}]', unicode: true), '')
        .replaceAll(RegExp(r'[\u{2600}-\u{26FF}]', unicode: true), '')
        .replaceAll(RegExp(r'[\u{2700}-\u{27BF}]', unicode: true), '')
        .replaceAll(RegExp(r'[\u{FE00}-\u{FEFF}]', unicode: true), '')
        .replaceAll(RegExp(r'  +'), ' ')
        .trim();
  }

  void _applySuggestion(String value) {
    final int? detectedCount = _extractPersonCount(value);

    setState(() {
      _keywordsController.text = value;
      _keywordsController.selection = TextSelection.collapsed(
        offset: _keywordsController.text.length,
      );

      if (detectedCount != null && detectedCount > 0) {
        _personCount = detectedCount;
      }

      _error = null;
    });
  }

  Widget _quickChip(String text) {
    return ActionChip(
      label: Text(text),
      onPressed: () => _applySuggestion(text),
    );
  }

  Widget _buildSuggestions(ThemeData theme) {
    final String input = _keywordsController.text.trim().toLowerCase();

    final List<String> filtered = input.isEmpty
        ? _allSuggestions.take(5).toList()
        : _allSuggestions
        .where((String s) => s.toLowerCase().contains(input))
        .toList();

    if (filtered.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      margin: const EdgeInsets.only(top: 16),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: theme.colorScheme.outline.withOpacity(0.18),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Suggestions',
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 10),
          ...filtered.map(
                (String suggestion) => ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(
                Icons.auto_awesome,
                color: theme.colorScheme.primary,
              ),
              title: Text(suggestion),
              onTap: () => _applySuggestion(suggestion),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildQuickPicks(ThemeData theme) {
    return Container(
      margin: const EdgeInsets.only(top: 18),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: theme.colorScheme.outline.withOpacity(0.18),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Quick Picks',
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _quickChip('Burger deal for 2'),
              _quickChip('BBQ combo for 3'),
              _quickChip('Pakistani meal for 4'),
              _quickChip('Chinese combo for 2'),
              _quickChip('Fast food deal for 2'),
              _quickChip('Biryani deal for 3'),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDealResult(ThemeData theme) {
    final CustomDealResponse deal = _dealResponse!;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: deal.success ? Colors.green : Colors.orange,
          width: 2,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 8,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                deal.success ? Icons.check_circle : Icons.info_outline,
                color: deal.success ? Colors.green : Colors.orange,
                size: 26,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  deal.success ? 'Deal Created!' : 'Need More Info',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: deal.success ? Colors.green : Colors.orange,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            _cleanMessage(deal.message),
            style: theme.textTheme.bodyMedium,
          ),
          if (deal.hasItems) ...[
            const Divider(height: 28),
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Deal Items',
                    style: theme.textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                Text(
                  'Qty',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(width: 48),
              ],
            ),
            const SizedBox(height: 8),
            ...deal.items.map(
                  (CustomDealItem item) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        item.itemName,
                        style: theme.textTheme.bodyMedium,
                      ),
                    ),
                    Container(
                      width: 32,
                      alignment: Alignment.center,
                      child: Text(
                        '${item.quantity}',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    SizedBox(
                      width: 72,
                      child: Text(
                        'Rs ${(item.price * item.quantity).toStringAsFixed(0)}',
                        textAlign: TextAlign.end,
                        style: TextStyle(
                          color: theme.colorScheme.primary,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const Divider(height: 24),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Price',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  'Rs ${deal.totalPrice.toStringAsFixed(0)}',
                  style: theme.textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: Colors.green,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: _isLoading ? null : _addToCart,
                icon: const Icon(Icons.shopping_cart),
                label: const Text('Add to Cart'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orangeAccent,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
          ],
          if (!deal.success && !deal.hasItems) ...[
            const SizedBox(height: 12),
            Text(
              'Try adding more detail in keywords, for example:\n'
                  'burger deal for 2\n'
                  'Pakistani meal for 4\n'
                  'BBQ combo for 3',
              style: theme.textTheme.bodySmall?.copyWith(
                color: Colors.grey[600],
              ),
            ),
          ],
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool canCreateDeal =
        !_isLoading && _keywordsController.text.trim().isNotEmpty;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Custom Deal'),
        centerTitle: true,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Person',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                _CounterButton(
                  icon: Icons.remove,
                  onTap: () {
                    if (_personCount > 1) {
                      setState(() => _personCount--);
                    }
                  },
                ),
                const SizedBox(width: 16),
                Container(
                  width: 80,
                  height: 48,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surface,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: theme.colorScheme.outline.withOpacity(0.4),
                    ),
                  ),
                  child: Text(
                    '$_personCount',
                    style: theme.textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                const SizedBox(width: 16),
                _CounterButton(
                  icon: Icons.add,
                  onTap: () => setState(() => _personCount++),
                ),
              ],
            ),
            const SizedBox(height: 28),
            Text(
              'Keywords',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _keywordsController,
              onChanged: (String value) {
                final int? detectedCount = _extractPersonCount(value);

                setState(() {
                  if (detectedCount != null &&
                      detectedCount > 0 &&
                      detectedCount != _personCount) {
                    _personCount = detectedCount;
                  }
                  _error = null;
                });
              },
              decoration: InputDecoration(
                hintText: 'Example: Burger deal for 2',
                prefixIcon: const Icon(Icons.search),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide(
                    color: theme.colorScheme.outline.withOpacity(0.4),
                  ),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide(
                    color: theme.colorScheme.outline.withOpacity(0.4),
                  ),
                ),
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 14,
                ),
              ),
              maxLines: 3,
              textInputAction: TextInputAction.done,
              onSubmitted: (_) {
                if (canCreateDeal) {
                  _createDeal();
                }
              },
            ),
            _buildSuggestions(theme),
            _buildQuickPicks(theme),
            const SizedBox(height: 28),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: canCreateDeal ? _createDeal : null,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orangeAccent,
                  foregroundColor: Colors.white,
                  disabledBackgroundColor: Colors.grey.shade400,
                  disabledForegroundColor: Colors.white70,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: _isLoading
                    ? const SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                )
                    : const Text(
                  'Create Deal',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 20),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Colors.red[50],
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.error_outline, color: Colors.red),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        _error!,
                        style: const TextStyle(color: Colors.red),
                      ),
                    ),
                  ],
                ),
              ),
            ],
            if (_dealResponse != null && !_isLoading) ...[
              const SizedBox(height: 24),
              _buildDealResult(theme),
            ],
          ],
        ),
      ),
    );
  }
}

class _CounterButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;

  const _CounterButton({
    required this.icon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final Color color = Theme.of(context).colorScheme.primary;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(24),
      child: Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: color, width: 2),
        ),
        child: Icon(icon, color: color, size: 22),
      ),
    );
  }
}
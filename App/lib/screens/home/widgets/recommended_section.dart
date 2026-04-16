// Phase 4 - Personalization Flutter UI
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:khaadim/models/recommendation_result.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/utils/ImageResolver.dart';

class RecommendedForYouSection extends StatefulWidget {
  final Future<RecommendationResult> future;
  const RecommendedForYouSection({super.key, required this.future});

  @override
  State<RecommendedForYouSection> createState() =>
      _RecommendedForYouSectionState();
}

class _RecommendedForYouSectionState extends State<RecommendedForYouSection>
    with SingleTickerProviderStateMixin {
  final Set<int> _adding = {};

  late AnimationController _shimmerController;
  late Animation<double> _shimmerAnim;

  @override
  void initState() {
    super.initState();
    _shimmerController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);
    _shimmerAnim = Tween<double>(begin: 0.3, end: 0.7).animate(
      CurvedAnimation(parent: _shimmerController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _shimmerController.dispose();
    super.dispose();
  }

  Future<void> _addToCart(BuildContext ctx, RecommendedItem item) async {
    final cart = Provider.of<CartProvider>(ctx, listen: false);
    if (cart.cartId == null) return;
    setState(() => _adding.add(item.itemId));
    try {
      await CartService.addItem(
        cartId: cart.cartId!,
        itemType: 'menu_item',
        itemId: item.itemId,
        quantity: 1,
      );
      await cart.sync();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('${item.itemName} added to cart!'),
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 1),
      ));
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('Could not add ${item.itemName}'),
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 1),
      ));
    } finally {
      if (mounted) setState(() => _adding.remove(item.itemId));
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<RecommendationResult>(
      future: widget.future,
      builder: (ctx, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return _buildShimmerSection(context);
        }
        final result = snapshot.data;
        if (result == null || result.recommendedItems.isEmpty) {
          return const SizedBox.shrink();
        }
        return _buildSection(context, result.recommendedItems);
      },
    );
  }

  Widget _buildSection(BuildContext context, List<RecommendedItem> items) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Row(
            children: [
              Container(
                width: 4,
                height: 20,
                decoration: BoxDecoration(
                  color: theme.colorScheme.primary,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                'Personalized For You',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.2,
                ),
              ),
            ],
          ),
        ),
        ListView.separated(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          clipBehavior: Clip.none,
          itemCount: items.length,
          separatorBuilder: (_, __) => const SizedBox(height: 10),
          itemBuilder: (ctx, i) => _buildItemCard(ctx, items[i]),
        ),
      ],
    );
  }

  Widget _buildItemCard(BuildContext context, RecommendedItem item) {
    final theme = Theme.of(context);
    final isAdding = _adding.contains(item.itemId);

    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
        border: Border.all(
          color: theme.colorScheme.outline.withOpacity(0.10),
        ),
      ),
      child: Row(
        children: [
          // Large image on the left
          ClipRRect(
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(14),
              bottomLeft: Radius.circular(14),
            ),
            child: Image.asset(
              ImageResolver.getMenuImage(item.category, item.itemName),
              width: 90,
              height: 90,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Container(
                width: 90,
                height: 90,
                color: Colors.grey.shade100,
                child: const Icon(Icons.fastfood, color: Colors.grey, size: 32),
              ),
            ),
          ),
          // Content on the right
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.itemName,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (item.reason.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(
                      item.reason,
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.onSurface.withOpacity(0.5),
                        height: 1.3,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                  const SizedBox(height: 8),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: SizedBox(
                      height: 28,
                      child: ElevatedButton(
                        onPressed:
                            isAdding ? null : () => _addToCart(context, item),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: theme.colorScheme.primary,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 18),
                          elevation: 0,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(20),
                          ),
                          minimumSize: Size.zero,
                          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        ),
                        child: isAdding
                            ? const SizedBox(
                                width: 12,
                                height: 12,
                                child: CircularProgressIndicator(
                                  strokeWidth: 1.5,
                                  color: Colors.white,
                                ),
                              )
                            : const Text(
                                '+ Add',
                                style: TextStyle(
                                    fontSize: 11, fontWeight: FontWeight.w600),
                              ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildShimmerSection(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: AnimatedBuilder(
            animation: _shimmerAnim,
            builder: (_, __) => Container(
              height: 18,
              width: 180,
              decoration: BoxDecoration(
                color: theme.colorScheme.onSurface
                    .withOpacity(_shimmerAnim.value * 0.12),
                borderRadius: BorderRadius.circular(6),
              ),
            ),
          ),
        ),
        ListView.separated(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: 3,
          separatorBuilder: (_, __) => const SizedBox(height: 10),
          itemBuilder: (_, __) => AnimatedBuilder(
            animation: _shimmerAnim,
            builder: (_, __) => Container(
              height: 90,
              decoration: BoxDecoration(
                color: theme.colorScheme.onSurface
                    .withOpacity(_shimmerAnim.value * 0.08),
                borderRadius: BorderRadius.circular(14),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

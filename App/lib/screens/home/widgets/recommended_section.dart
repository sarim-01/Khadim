// Phase 4 - Personalization Flutter UI
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:khaadim/models/recommendation_result.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/services/personalization_service.dart';
import 'package:khaadim/utils/ImageResolver.dart';

class RecommendedForYouSection extends StatefulWidget {
  final Future<RecommendationResult> future;
  const RecommendedForYouSection({Key? key, required this.future}) : super(key: key);

  @override
  State<RecommendedForYouSection> createState() =>
      _RecommendedForYouSectionState();
}

class _RecommendedForYouSectionState extends State<RecommendedForYouSection>
    with SingleTickerProviderStateMixin {
  final Set<int> _adding = {};

  // Shimmer animation controller
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
      if (mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(
          content: Text('${item.itemName} added to cart!'),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 1),
        ));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(
          content: Text('Could not add ${item.itemName}'),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 1),
        ));
      }
    } finally {
      if (mounted) setState(() => _adding.remove(item.itemId));
    }
  }

  Widget build(BuildContext context) {
    return FutureBuilder<RecommendationResult>(
      future: widget.future,
      builder: (ctx, snapshot) {
        // Loading — shimmer cards
        if (snapshot.connectionState == ConnectionState.waiting) {
          return _buildShimmerSection(context);
        }

        // Error or empty — silent fail
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
              const Text('🍽️', style: TextStyle(fontSize: 18)),
              const SizedBox(width: 8),
              Text(
                'Personalized For You',
                style: theme.textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: theme.colorScheme.primary,
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
          separatorBuilder: (_, __) => const SizedBox(height: 12),
          itemBuilder: (ctx, i) => _buildItemCard(ctx, items[i]),
        ),
      ],
    );
  }

  Widget _buildItemCard(BuildContext context, RecommendedItem item) {
    final theme = Theme.of(context);
    final isAdding = _adding.contains(item.itemId);

    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.06),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
        border: Border.all(
          color: theme.colorScheme.outline.withOpacity(0.12),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Item Image
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: Image.asset(
                ImageResolver.getMenuImage(item.category, item.itemName),
                width: 48,
                height: 48,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => Container(
                  width: 48,
                  height: 48,
                  color: Colors.grey.shade200,
                  child: const Icon(Icons.fastfood, color: Colors.grey),
                ),
              ),
            ),
            const SizedBox(height: 8),

            // Item name
            Text(
              item.itemName,
              style: theme.textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: 4),

            // Reason tag
            if (item.reason.isNotEmpty)
              Text(
                item.reason,
                style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.onSurface.withOpacity(0.5),
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),

            const SizedBox(height: 8),

            // Add button
            SizedBox(
              width: double.infinity,
              height: 30,
              child: ElevatedButton(
                onPressed: isAdding ? null : () => _addToCart(context, item),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orangeAccent,
                  foregroundColor: Colors.white,
                  padding: EdgeInsets.zero,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
                child: isAdding
                    ? const SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Text('Add', style: TextStyle(fontSize: 12)),
              ),
            ),
          ],
        ),
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
              height: 20,
              width: 200,
              decoration: BoxDecoration(
                color: theme.colorScheme.onSurface.withOpacity(_shimmerAnim.value * 0.15),
                borderRadius: BorderRadius.circular(6),
              ),
            ),
          ),
        ),
        ListView.separated(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: 4,
          separatorBuilder: (_, __) => const SizedBox(height: 12),
          itemBuilder: (_, __) => AnimatedBuilder(
            animation: _shimmerAnim,
            builder: (_, __) => Container(
              height: 150,
              width: double.infinity,
              decoration: BoxDecoration(
                  color: theme.colorScheme.onSurface
                      .withOpacity(_shimmerAnim.value * 0.1),
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
            ),
        ),
      ],
    );
  }
}

// Phase 4 - Personalization Flutter UI
import 'package:flutter/material.dart';

import 'package:khaadim/models/recommendation_result.dart';
import 'package:khaadim/services/personalization_service.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/utils/ImageResolver.dart';
import 'package:provider/provider.dart';

class DealsYouLoveSection extends StatefulWidget {
  final Future<RecommendationResult> future;
  const DealsYouLoveSection({Key? key, required this.future}) : super(key: key);

  @override
  State<DealsYouLoveSection> createState() => _DealsYouLoveSectionState();
}

class _DealsYouLoveSectionState extends State<DealsYouLoveSection>
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

  Future<void> _addDeal(RecommendedDeal deal) async {
    final cartId = context.read<CartProvider>().cartId;
    if (cartId == null) return;

    setState(() => _adding.add(deal.dealId));

    try {
      await CartService.addItem(
        cartId: cartId,
        itemType: 'deal',
        itemId: deal.dealId,
        quantity: 1,
      );
      await context.read<CartProvider>().sync();

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text("${deal.dealName} added!"),
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 1),
          ),
        );
      }
    } catch (_) {
    } finally {
      if (mounted) setState(() => _adding.remove(deal.dealId));
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
        if (result == null || result.recommendedDeals.isEmpty) {
          return const SizedBox.shrink();
        }

        return _buildSection(context, result.recommendedDeals);
      },
    );
  }

  Widget _buildSection(BuildContext context, List<RecommendedDeal> deals) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Row(
            children: [
              const Text('🎁', style: TextStyle(fontSize: 18)),
              const SizedBox(width: 8),
              Text(
                "Deals You'll Love",
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
          itemCount: deals.length,
          separatorBuilder: (_, __) => const SizedBox(height: 12),
          itemBuilder: (ctx, i) => _buildDealCard(ctx, deals[i]),
        ),
      ],
    );
  }

  Widget _buildDealCard(BuildContext context, RecommendedDeal deal) {
    final theme = Theme.of(context);
    final isAdding = _adding.contains(deal.dealId);

    return Container(
        width: double.infinity,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              theme.colorScheme.primary.withOpacity(0.85),
              theme.colorScheme.primary,
            ],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(14),
          boxShadow: [
            BoxShadow(
              color: theme.colorScheme.primary.withOpacity(0.25),
              blurRadius: 8,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Deal Image
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: Image.asset(
                  ImageResolver.getDealImage(deal.dealName),
                  width: 48,
                  height: 48,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => Container(
                    width: 48,
                    height: 48,
                    color: Colors.white.withOpacity(0.2),
                    child: const Icon(Icons.local_offer, color: Colors.white),
                  ),
                ),
              ),
              const SizedBox(height: 8),

              // Deal name
              Text(
                deal.dealName,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 4),

              // Reason tag
              if (deal.reason.isNotEmpty)
                Text(
                  deal.reason,
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: Colors.white.withOpacity(0.75),
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),

              const SizedBox(height: 8),

              // Deal actions
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  GestureDetector(
                    onTap: () {
                      showDialog(
                        context: context,
                        builder: (_) => AlertDialog(
                          title: Text(deal.dealName),
                          content: Text(deal.items.isNotEmpty ? deal.items : "Includes multiple items from our menu."),
                          actions: [
                            TextButton(
                              onPressed: () => Navigator.pop(context),
                              child: const Text("Close"),
                            )
                          ],
                        ),
                      );
                    },
                    child: Row(
                      children: [
                        Text(
                          'View items',
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(width: 4),
                        const Icon(Icons.arrow_forward_ios_rounded,
                            color: Colors.white, size: 10),
                      ],
                    ),
                  ),

                  // Add button
                  SizedBox(
                    height: 32,
                    child: ElevatedButton(
                      onPressed: isAdding ? null : () => _addDeal(deal),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.white,
                        foregroundColor: theme.colorScheme.primary,
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        elevation: 0,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      child: isAdding
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text(
                              "Add",
                              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
                            ),
                    ),
                  ),
                ],
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
              width: 180,
              decoration: BoxDecoration(
                color: theme.colorScheme.onSurface
                    .withOpacity(_shimmerAnim.value * 0.15),
                borderRadius: BorderRadius.circular(6),
              ),
            ),
          ),
        ),
        ListView.separated(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: 3,
          separatorBuilder: (_, __) => const SizedBox(height: 12),
          itemBuilder: (_, __) => AnimatedBuilder(
            animation: _shimmerAnim,
            builder: (_, __) => Container(
              height: 140,
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

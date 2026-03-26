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
    if (cartId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Cart not ready, please try again.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }
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
            content: Text('${deal.dealName} added!'),
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 1),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Could not add ${deal.dealName}'),
            behavior: SnackBarBehavior.floating,
            backgroundColor: Colors.redAccent,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _adding.remove(deal.dealId));
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
                "Deals You'll Love",
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
          itemCount: deals.length,
          separatorBuilder: (_, __) => const SizedBox(height: 10),
          itemBuilder: (ctx, i) => _buildDealCard(ctx, deals[i]),
        ),
      ],
    );
  }

  Widget _buildDealCard(BuildContext context, RecommendedDeal deal) {
    final theme = Theme.of(context);
    final isAdding = _adding.contains(deal.dealId);

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
          // Deal image — left side
          ClipRRect(
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(14),
              bottomLeft: Radius.circular(14),
            ),
            child: Image.asset(
              ImageResolver.getDealImage(deal.dealName),
              width: 90,
              height: 90,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Container(
                width: 90,
                height: 90,
                color: Colors.grey.shade100,
                child: const Icon(Icons.local_offer_outlined,
                    color: Colors.grey, size: 32),
              ),
            ),
          ),
          // Content — right side
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    deal.dealName,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (deal.reason.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(
                      deal.reason,
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.onSurface.withOpacity(0.5),
                        height: 1.3,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      // View items link
                      GestureDetector(
                        onTap: () {
                          showDialog(
                            context: context,
                            builder: (_) => AlertDialog(
                              title: Text(deal.dealName),
                              content: Text(deal.items.isNotEmpty
                                  ? deal.items
                                  : 'Includes multiple items from our menu.'),
                              actions: [
                                TextButton(
                                  onPressed: () => Navigator.pop(context),
                                  child: const Text('Close'),
                                ),
                              ],
                            ),
                          );
                        },
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              'View items',
                              style: theme.textTheme.labelSmall?.copyWith(
                                color: theme.colorScheme.primary,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(width: 2),
                            Icon(Icons.arrow_forward_ios_rounded,
                                color: theme.colorScheme.primary, size: 10),
                          ],
                        ),
                      ),
                      const Spacer(),
                      // Add button
                      SizedBox(
                        height: 28,
                        child: ElevatedButton(
                          onPressed: isAdding ? null : () => _addDeal(deal),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: theme.colorScheme.primary,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(horizontal: 16),
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
                    ],
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
              width: 160,
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

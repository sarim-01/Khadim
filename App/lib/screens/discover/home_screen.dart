import 'package:flutter/material.dart';

import 'package:khaadim/screens/cart/cart_screen.dart';
import 'package:khaadim/screens/discover/upsell_popup.dart';
import 'package:khaadim/screens/discover/custom_deal_screen.dart';
import 'package:khaadim/screens/home/widgets/recommended_section.dart';
import 'package:khaadim/screens/home/widgets/deals_you_love_section.dart';
import 'package:khaadim/services/personalization_service.dart';
import 'package:khaadim/models/recommendation_result.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  static bool _upsellShown = false;

  late Future<RecommendationResult> _recommendationFuture;

  @override
  void initState() {
    super.initState();
    _recommendationFuture = PersonalizationService.getRecommendations(topK: 10);
    // Show upsell popup only once per app session
    if (!_upsellShown) {
      _upsellShown = true;
      WidgetsBinding.instance.addPostFrameCallback((_) => _showUpsellPopup());
    }
  }

  void _showUpsellPopup() {
    showDialog(
      context: context,
      barrierDismissible: true,
      barrierColor: Colors.black.withOpacity(0.6),
      builder: (_) => const UpsellPopup(),
    );
  }

  Future<void> _handleRefresh() async {
    // Fetch in the background first — don't call setState until data arrives.
    // Calling setState early causes a full widget rebuild which resets scroll position.
    final next = PersonalizationService.getRecommendations(topK: 10);
    try {
      await next;
    } catch (_) {
      // Ignore fetch errors; indicator will still dismiss
    }
    if (mounted) {
      setState(() {
        _recommendationFuture = next;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SafeArea(
      child: Scaffold(
        appBar: AppBar(
          title: Text(
            "Special deals just for you",
            style: theme.textTheme.bodyLarge?.copyWith(
              fontWeight: FontWeight.w600,
            ),
          ),
          actions: [
            IconButton(
              icon: const Icon(Icons.shopping_cart_outlined),
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const CartScreen()),
                );
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
              // Custom Deal Card at the top
              _buildCustomDealCard(context),
              const SizedBox(height: 20),

              // ── Phase 4: AI-Personalized sections ──
              FutureBuilder<RecommendationResult>(
                future: _recommendationFuture,
                builder: (ctx, snapshot) {
                  final result = snapshot.data;
                  final isNewUser =
                      snapshot.connectionState == ConnectionState.done &&
                          result != null &&
                          result.source == 'new_user';

                  if (isNewUser) {
                    return Container(
                      margin: const EdgeInsets.symmetric(
                          horizontal: 0, vertical: 24),
                      padding: const EdgeInsets.all(24),
                      decoration: BoxDecoration(
                        color: Colors.grey.shade100,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.restaurant_menu_outlined,
                              size: 48, color: Colors.grey),
                          const SizedBox(height: 12),
                          const Text(
                            'Your personalized feed is empty',
                            style: TextStyle(
                                fontWeight: FontWeight.bold, fontSize: 16),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            'Order and rate items to unlock recommendations tailored just for you! 🍽️',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                                color: Colors.grey.shade600, fontSize: 13),
                          ),
                        ],
                      ),
                    );
                  }

                  // Normal state — show both personalization sections
                  return Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      RecommendedForYouSection(future: _recommendationFuture),
                      const SizedBox(height: 20),
                      DealsYouLoveSection(future: _recommendationFuture),
                      const SizedBox(height: 20),
                    ],
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Custom Deal Card
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
                              horizontal: 10, vertical: 4),
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
                              Icon(Icons.auto_awesome,
                                  color: theme.colorScheme.primary, size: 12),
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
                              horizontal: 16, vertical: 8),
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
                              Icon(Icons.arrow_forward_rounded,
                                  color: Colors.white, size: 15),
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

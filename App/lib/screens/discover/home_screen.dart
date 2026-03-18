import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/screens/cart/cart_screen.dart';
import 'package:khaadim/screens/discover/upsell_popup.dart';
import 'package:khaadim/screens/discover/custom_deal_screen.dart';
import 'package:khaadim/screens/home/widgets/recommended_section.dart';
import 'package:khaadim/screens/home/widgets/deals_you_love_section.dart';
import 'package:khaadim/services/personalization_service.dart';
import 'package:khaadim/models/recommendation_result.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({Key? key}) : super(key: key);

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  static bool _upsellShown = false;

  late final Future<RecommendationResult> _recommendationFuture;

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

        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Custom Deal Card at the top
            _buildCustomDealCard(context),
            const SizedBox(height: 20),

            // ── Phase 4: AI-Personalized sections ──
            RecommendedForYouSection(future: _recommendationFuture),
            const SizedBox(height: 20),

            DealsYouLoveSection(future: _recommendationFuture),
            const SizedBox(height: 20),
          ],
        ),
      ),
    );
  }

  /// Custom Deal Card
  Widget _buildCustomDealCard(BuildContext context) {
    final theme = Theme.of(context);

    return GestureDetector(
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const CustomDealScreen()),
        );
      },
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFFFF9800), Color(0xFFFF5722)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.orange.withOpacity(0.3),
              blurRadius: 10,
              offset: const Offset(0, 5),
            ),
          ],
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(
                        Icons.auto_awesome,
                        color: Colors.white,
                        size: 24,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        "Create Custom Deal",
                        style: theme.textTheme.titleMedium?.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    "Tell AI what you want & get a personalized deal!",
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: Colors.white.withOpacity(0.9),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 8,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          "Try Now",
                          style: TextStyle(
                            color: Color(0xFFFF5722),
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        SizedBox(width: 4),
                        Icon(
                          Icons.arrow_forward,
                          color: Color(0xFFFF5722),
                          size: 18,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const Icon(
              Icons.restaurant_menu,
              color: Colors.white,
              size: 50,
            ),
          ],
        ),
      ),
    );
  }
}
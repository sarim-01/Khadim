import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:khaadim/screens/discover/home_screen.dart';
import 'package:khaadim/screens/menu/menu_screen.dart';
import 'package:khaadim/screens/discover/offer_screen.dart';
import 'package:khaadim/screens/profile/profile_screen.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/screens/cart/cart_screen.dart';
import 'package:khaadim/widgets/mic_button.dart';
import 'package:khaadim/widgets/voice_order_handler.dart';
import 'package:khaadim/widgets/voice_nav_callbacks.dart';
import 'package:khaadim/screens/support/favorites_screen.dart';


class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _currentIndex = 0;
  late final VoiceOrderHandler _voiceHandler;

  final List<Widget> _screens = const [
    HomeScreen(key: ValueKey('home')),
    MenuScreen(key: ValueKey('menu')),
    OffersScreen(key: ValueKey('offer')),
    ProfileScreen(key: ValueKey('profile')),
  ];

  @override
  void initState() {
    super.initState();
    _voiceHandler = VoiceOrderHandler();
    _voiceHandler.init();
    _voiceHandler.setNavCallbacks(
      VoiceNavCallbacks(
        switchTab: (index) => _onTabTapped(index),

        // Voice: "show BBQ menu" / "show desi items" / "show drinks"
        // Push a pre-filtered MenuScreen so the cuisine/category chips are
        // already selected when the screen opens.
        openMenuWithFilter: ({String? cuisine, String? category}) {
          if (cuisine != null || category != null) {
            Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) => MenuScreen(
                  initialCuisine: cuisine,
                  initialCategory: category,
                ),
              ),
            );
          } else {
            _onTabTapped(1);
          }
        },

        openCart: () {
          Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const CartScreen()),
          );
        },
        openCheckout: ({String paymentMethod = 'COD'}) {
          Navigator.pushNamed(
            context,
            '/checkout',
            arguments: {'payment_method': paymentMethod},
          );
        },
        openOrders: () {
          Navigator.pushNamed(context, '/order_history');
        },
        openFavourites: () {
          Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const FavoritesScreen()),
          );
        },
        openRecommendations: () {
          _onTabTapped(0);
        },

        // Voice: "show BBQ deals" / "show deals for 2 people"
        // Push a pre-filtered OffersScreen with cuisine + serving chips set.
        openDealsWithFilter: ({
          String? cuisineFilter,
          String? servingFilter,
          int? highlightDealId,
        }) {
          if (cuisineFilter != null ||
              servingFilter != null ||
              highlightDealId != null) {
            Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) => OffersScreen(
                  initialCuisine: cuisineFilter,
                  initialServing: servingFilter,
                  highlightDealId: highlightDealId,
                ),
              ),
            );
          } else {
            _onTabTapped(2);
          }
        },
      ),
    );
  }

  void _onTabTapped(int index) {
    if (index == _currentIndex) return;
    setState(() => _currentIndex = index);
  }

  @override
  void dispose() {
    _voiceHandler.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cart = Provider.of<CartProvider>(context);
    final theme = Theme.of(context);

    return Scaffold(
      body: AnimatedSwitcher(
        duration: const Duration(milliseconds: 300),
        transitionBuilder: (child, animation) {
          final offset = Tween<Offset>(
            begin: const Offset(0.2, 0),
            end: Offset.zero,
          ).animate(animation);
          return SlideTransition(position: offset, child: child);
        },
        child: _screens[_currentIndex],
      ),

      // --------------------------
      //   Bottom Navigation
      // --------------------------
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: _onTabTapped,
        type: BottomNavigationBarType.fixed,
        selectedItemColor: theme.colorScheme.primary,
        unselectedItemColor: theme.textTheme.bodyMedium?.color,
        items: const [
          BottomNavigationBarItem(
              icon: Icon(Icons.home_outlined), label: "Home"),
          BottomNavigationBarItem(
              icon: Icon(Icons.restaurant_menu), label: "Menu"),
          BottomNavigationBarItem(
              icon: Icon(Icons.local_offer_outlined), label: "Deals"),
          BottomNavigationBarItem(
              icon: Icon(Icons.person_outline), label: "Profile"),
        ],
      ),

      // ---------------------------------------
      //   Floating Button: Voice + Cart Badge
      // ---------------------------------------
      floatingActionButton: Stack(
        alignment: Alignment.bottomRight,
        children: [
          // Voice mic button (hold to record) - no extra screen.
          AnimatedBuilder(
            animation: _voiceHandler,
            builder: (_, __) => MicButton(
              isRecording: _voiceHandler.isRecording,
              isProcessing: _voiceHandler.isProcessing,
              onPressDown: () => _voiceHandler.onMicDown(context),
              onPressUp: () => _voiceHandler.onMicUp(context),
              onCancel: _voiceHandler.onMicCancel,
            ),
          ),

          // Cart button with badge
          Positioned(
            right: 75,
            bottom: 0,
            child: GestureDetector(
              onTap: () {
                if (cart.items.isNotEmpty) {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => const CartScreen(),
                    ),
                  );
                }
              },
              child: Stack(
                alignment: Alignment.center,
                children: [
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Colors.black87,
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(Icons.shopping_cart,
                        color: Colors.white, size: 24),
                  ),

                  // Cart badge
                  if (cart.items.isNotEmpty)
                    Positioned(
                      right: 0,
                      top: 0,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.redAccent,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(
                          cart.items.length.toString(),
                          style: const TextStyle(
                              color: Colors.white, fontSize: 12),
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
}

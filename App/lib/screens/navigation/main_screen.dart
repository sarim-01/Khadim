import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:khaadim/screens/discover/home_screen.dart';
import 'package:khaadim/screens/menu/menu_screen.dart';
import 'package:khaadim/screens/discover/offer_screen.dart';
import 'package:khaadim/screens/profile/profile_screen.dart';
import 'package:khaadim/screens/chat/chat_bottom_sheet.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/screens/cart/cart_screen.dart';

class MainScreen extends StatefulWidget {
  const MainScreen({Key? key}) : super(key: key);

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _currentIndex = 0;

  final List<Widget> _screens = const [
    HomeScreen(key: ValueKey('home')),
    MenuScreen(key: ValueKey('menu')),
    OffersScreen(key: ValueKey('offer')),
    ProfileScreen(key: ValueKey('profile')),
  ];

  void _onTabTapped(int index) {
    if (index == _currentIndex) return;
    setState(() => _currentIndex = index);
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
          BottomNavigationBarItem(icon: Icon(Icons.home_outlined), label: "Home"),
          BottomNavigationBarItem(icon: Icon(Icons.restaurant_menu), label: "Menu"),
          BottomNavigationBarItem(icon: Icon(Icons.local_offer_outlined), label: "Deals"),
          BottomNavigationBarItem(icon: Icon(Icons.person_outline), label: "Profile"),
        ],
      ),

      // ---------------------------------------
      //   Floating Button: Voice + Cart Badge
      // ---------------------------------------
      floatingActionButton: Stack(
        alignment: Alignment.bottomRight,
        children: [
          // Voice AI button
          FloatingActionButton(
            backgroundColor: theme.colorScheme.primary,
            foregroundColor: Colors.black,
            heroTag: "voiceButton",
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
                        mode: "voice",
                        scrollController: controller,
                      );
                    },
                  );
                },
              );
            },
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
                        padding:
                        const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
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

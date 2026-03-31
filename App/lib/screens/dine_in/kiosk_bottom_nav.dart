import 'package:flutter/material.dart';

class KioskBottomNav extends StatelessWidget {
  final int currentIndex;

  const KioskBottomNav({
    super.key,
    required this.currentIndex,
  });

  static const List<String> _routes = <String>[
    '/kiosk-home',
    '/kiosk-menu',
    '/kiosk-deals',
    '/kiosk-orders',
  ];

  void _onTap(BuildContext context, int index) {
    final targetRoute = _routes[index];
    final currentRoute = ModalRoute.of(context)?.settings.name;

    if (currentRoute == targetRoute) {
      return;
    }

    Navigator.pushReplacementNamed(context, targetRoute);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return BottomNavigationBar(
      currentIndex: currentIndex,
      onTap: (index) => _onTap(context, index),
      type: BottomNavigationBarType.fixed,
      selectedItemColor: theme.colorScheme.primary,
      unselectedItemColor: theme.textTheme.bodyMedium?.color,
      items: const [
        BottomNavigationBarItem(icon: Icon(Icons.home), label: 'Home'),
        BottomNavigationBarItem(icon: Icon(Icons.restaurant_menu), label: 'Menu'),
        BottomNavigationBarItem(icon: Icon(Icons.local_offer), label: 'Deals'),
        BottomNavigationBarItem(icon: Icon(Icons.receipt_long), label: 'Orders'),
      ],
    );
  }
}
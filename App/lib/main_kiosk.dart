import 'package:flutter/material.dart';
import 'package:khaadim/app_config.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/providers/dine_in_provider.dart';
import 'package:khaadim/screens/cart/cart_screen.dart';
import 'package:khaadim/screens/deals/deal_screen.dart';
import 'package:khaadim/screens/dine_in/dine_in_home_screen.dart';
import 'package:khaadim/screens/dine_in/dine_in_order_history_screen.dart';
import 'package:khaadim/screens/dine_in/table_pin_screen.dart';
import 'package:khaadim/screens/menu/menu_screen.dart';
import 'package:khaadim/screens/orders/order_tracking_screen.dart';
import 'package:khaadim/themes/app_theme.dart';
import 'package:provider/provider.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  AppConfig.flavor = AppFlavor.kiosk;

  final dineInProvider = DineInProvider();
  final hasActiveSession = await dineInProvider.restoreSession();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => CartProvider()),
        ChangeNotifierProvider<DineInProvider>.value(value: dineInProvider),
      ],
      child: KhadimKioskApp(hasActiveSession: hasActiveSession),
    ),
  );
}

class KhadimKioskApp extends StatelessWidget {
  final bool hasActiveSession;

  const KhadimKioskApp({super.key, required this.hasActiveSession});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Khadim Restaurant',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: ThemeMode.system,
      initialRoute: hasActiveSession ? '/kiosk-home' : '/kiosk-login',
      routes: {
        '/kiosk-login': (_) => const TablePinScreen(),
        '/kiosk-home': (_) => const DineInHomeScreen(),
        '/kiosk-menu': (_) => const MenuScreen(),
        '/kiosk-deals': (_) => const DealScreen(),
        '/kiosk-cart': (_) => const CartScreen(),
        '/kiosk-orders': (_) => const DineInOrderHistoryScreen(),
        '/kiosk-tracking': (_) => const OrderTrackingScreen(orderId: 0),

        // Backward-compatible aliases for existing navigation calls.
        '/kiosk/login': (_) => const TablePinScreen(),
        '/kiosk/home': (_) => const DineInHomeScreen(),
        '/kiosk/menu': (_) => const MenuScreen(),
        '/kiosk/deals': (_) => const DealScreen(),
        '/kiosk/cart': (_) => const CartScreen(),
        '/kiosk/orders': (_) => const DineInOrderHistoryScreen(),
        '/kiosk/tracking': (_) => const OrderTrackingScreen(orderId: 0),
      },
      onUnknownRoute: (settings) {
        return MaterialPageRoute(
          builder: (_) => const TablePinScreen(),
        );
      },
    );
  }
}

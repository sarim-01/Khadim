import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'themes/app_theme.dart';
import 'app_config.dart';

// Providers
import 'providers/cart_provider.dart';
import 'providers/dine_in_provider.dart';

// Screens
import 'package:khaadim/screens/auth/splash_screen.dart';
import 'package:khaadim/screens/auth/login_screen.dart';
import 'package:khaadim/screens/auth/signup_screen.dart';
import 'package:khaadim/screens/navigation/main_screen.dart';
import 'package:khaadim/screens/menu/menu_screen.dart';
import 'package:khaadim/screens/discover/offer_screen.dart';
import 'package:khaadim/screens/profile/profile_screen.dart';
import 'package:khaadim/screens/cart/cart_screen.dart';
import 'package:khaadim/screens/checkout/checkout_screen.dart';
import 'package:khaadim/screens/payments/add_payment_screen.dart';
import 'package:khaadim/screens/payments/payment_method_screen.dart';
import 'package:khaadim/screens/orders/order_history_screen.dart';
import 'package:khaadim/screens/devtools/test_urdu_tts.dart';
import 'package:khaadim/screens/admin/admin_shell.dart';
import 'package:khaadim/screens/dine_in/table_pin_screen.dart';
import 'package:khaadim/screens/dine_in/dine_in_home_screen.dart';
import 'package:khaadim/screens/dine_in/my_table_screen.dart';

void main() {
  AppConfig.flavor = AppFlavor.customer; // ← ADDED
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => CartProvider()),
        ChangeNotifierProvider(create: (_) => DineInProvider()),
      ],
      child: const KhaadimApp(),
    ),
  );
}

class KhaadimApp extends StatelessWidget {
  final String initialRoute;

  const KhaadimApp({
    super.key,
    this.initialRoute = '/splash',
  });

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Khaadim',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: ThemeMode.system,
      initialRoute: initialRoute,
      routes: {
        '/splash': (context) => const SplashScreen(),
        '/login': (context) => const LoginScreen(),
        '/signup': (context) => const SignupScreen(),
        '/main': (context) => const MainScreen(),
        '/menu': (context) => const MenuScreen(),
        '/offer': (context) => const OffersScreen(),
        '/profile': (context) => const ProfileScreen(),
        '/cart': (context) => const CartScreen(),
        '/checkout': (context) {
          final args = ModalRoute.of(context)?.settings.arguments;

          String rawMethod = 'COD';
          if (args is String && args.trim().isNotEmpty) {
            rawMethod = args;
          } else if (args is Map) {
            final dynamic method =
                args['payment_method'] ?? args['paymentMethod'];
            if (method is String && method.trim().isNotEmpty) {
              rawMethod = method;
            }
          }

          final normalized = rawMethod.trim().toUpperCase();
          final paymentMethod =
          normalized.contains('CARD') || normalized.contains('DEBIT')
              ? 'CARD'
              : 'COD';

          return CheckoutScreen(initialPaymentMethod: paymentMethod);
        },
        '/payment_methods': (context) => const PaymentMethodsScreen(),
        '/add_payment': (context) => const AddPaymentScreen(),
        '/order_history': (context) => const OrderHistoryScreen(),
        '/ttsTest': (context) => const TestUrduTTSPage(),
        '/admin': (context) => const AdminShell(),
        '/dine-in/table-login': (context) => const TablePinScreen(),
        '/dine-in/home': (context) => const DineInHomeScreen(),
        '/dine-in/my-table': (context) => const MyTableScreen(),
      },
      onUnknownRoute: (settings) {
        return MaterialPageRoute(
          builder: (context) => const SplashScreen(),
        );
      },
    );
  }
}
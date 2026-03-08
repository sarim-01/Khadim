import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'themes/app_theme.dart';

// Providers
import 'providers/cart_provider.dart';

// Screens
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
import 'package:khaadim/screens/orders/order_confirmation_screen.dart';
import 'package:khaadim/screens/orders/order_history_screen.dart';
import 'package:khaadim/screens/devtools/test_urdu_tts.dart';

void main() {
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => CartProvider()),
      ],
      child: const KhaadimApp(),
    ),
  );
}

class KhaadimApp extends StatelessWidget {
  const KhaadimApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Khaadim',
      debugShowCheckedModeBanner: false,

      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: ThemeMode.system,

      initialRoute: '/splash',

      routes: {
        '/splash': (context) => const SplashScreen(),
        '/login': (context) => const LoginScreen(),
        '/signup': (context) => const SignupScreen(),
        '/main': (context) => const MainScreen(),
        '/menu': (context) => const MenuScreen(),
        '/offer': (context) => const OffersScreen(),
        '/profile': (context) => const ProfileScreen(),
        '/cart': (context) => const CartScreen(),
        '/checkout': (context) => const CheckoutScreen(),
        '/payment_methods': (context) => const PaymentMethodsScreen(),
        '/add_payment': (context) => const AddPaymentScreen(),
        '/order_history': (context) => const OrderHistoryScreen(),
        '/ttsTest': (context) => const TestUrduTTSPage(),
      },

      onUnknownRoute: (settings) {
        return MaterialPageRoute(
          builder: (context) => const SplashScreen(),
        );
      },
    );
  }
}

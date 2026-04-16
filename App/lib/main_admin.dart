import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:khaadim/app_config.dart';
import 'package:khaadim/themes/app_theme.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/providers/dine_in_provider.dart';
import 'package:khaadim/screens/admin/admin_shell.dart';
import 'package:khaadim/screens/admin/admin_login_screen.dart';
import 'package:khaadim/screens/auth/login_screen.dart';
import 'package:khaadim/screens/auth/signup_screen.dart';
import 'package:khaadim/screens/navigation/main_screen.dart';

void main() {
  AppConfig.flavor = AppFlavor.admin;
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => CartProvider()),
        ChangeNotifierProvider(create: (_) => DineInProvider()),
      ],
      child: const KhaadimAdminApp(),
    ),
  );
}

class KhaadimAdminApp extends StatelessWidget {
  const KhaadimAdminApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Khaadim Admin',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: ThemeMode.system,
      initialRoute: '/admin-login',       // ← start here, not AdminShell
      routes: {
        '/admin-login': (_) => const AdminLoginScreen(),
        '/admin':       (_) => const AdminShell(),
        '/login':       (_) => const LoginScreen(),
        '/signup':      (_) => const SignupScreen(),
        '/main':        (_) => const MainScreen(),
      },
      onUnknownRoute: (_) =>
          MaterialPageRoute(builder: (_) => const AdminLoginScreen()),
    );
  }
}
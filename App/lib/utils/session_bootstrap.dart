import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/token_storage.dart';
import '../services/auth_service.dart';
import '../services/api_client.dart';
import '../providers/cart_provider.dart';

class SessionBootstrap {
  static Future<void> run(BuildContext context) async {
    try {
      final token = await TokenStorage.getToken();
      if (!context.mounted) return;
      if (token == null) {
        _goLogin(context);
        return;
      }

      final me = await AuthService.me();
      if (!context.mounted) return;
      final user = me['user'] ?? me; // sometimes backend wraps it in 'user'
      final userId = (user['user_id'] ?? user['userId']).toString();
      final email = (user['email'] ?? '').toString();

      if (email == 'admin@gmail.com') {
        _goAdmin(context);
        return;
      }

      await context.read<CartProvider>().initCart(userId);
      if (!context.mounted) return;

      _goMain(context);
    } on ApiException catch (e) {
      if (e.isUnauthorized) {
        await TokenStorage.clearToken();
        if (!context.mounted) return;
        _goLogin(context);
        return;
      }

      // Keep token for transient failures
      if (!context.mounted) return;
      _goLogin(context);
    } catch (_) {
      if (!context.mounted) return;
      _goLogin(context);
    }
  }

  static void _goLogin(BuildContext context) {
    if (!context.mounted) return;
    Navigator.pushReplacementNamed(context, '/login');
  }

  static void _goMain(BuildContext context) {
    if (!context.mounted) return;
    Navigator.pushReplacementNamed(context, '/main');
  }

  static void _goAdmin(BuildContext context) {
    if (!context.mounted) return;
    Navigator.pushReplacementNamed(context, '/admin');
  }
}

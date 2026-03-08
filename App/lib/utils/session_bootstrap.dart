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
      if (token == null) {
        _goLogin(context);
        return;
      }

      final me = await AuthService.me();
      final userId = (me['user_id'] ?? me['userId']).toString();

      await context.read<CartProvider>().initCart(userId);

      _goMain(context);
    } on ApiException catch (e) {
      if (e.isUnauthorized) {
        await TokenStorage.clearToken();
        _goLogin(context);
        return;
      }

      // Keep token for transient failures
      _goLogin(context);
    } catch (_) {
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
}
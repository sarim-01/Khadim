import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:provider/provider.dart';

import 'package:khaadim/services/api_client.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/services/chat_service.dart';
import 'package:khaadim/services/conversation_memory.dart';
import 'package:khaadim/services/voice_deal_service.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/widgets/voice_nav_callbacks.dart';

class VoiceCommandResult {
  final bool success;
  final String actionTaken;
  final String reply;
  final String transcript;
  final bool navigated;

  const VoiceCommandResult({
    this.success = false,
    this.actionTaken = '',
    this.reply = '',
    this.transcript = '',
    this.navigated = false,
  });
}

class VoiceCommandService {
  late final VoiceDealService _dealService;

  VoiceCommandService({FlutterTts? tts}) {
    _dealService = VoiceDealService(tts ?? FlutterTts());
  }

  // ── Urdu path ─────────────────────────────────────────────
  Future<VoiceCommandResult> executeFromResponse({
    required String transcript,
    required Map<String, dynamic> response,
    required BuildContext context,
    required String sessionId,
    required String language,
    VoiceNavCallbacks? nav,
    ConversationMemory? memory,
  }) async {
    try {
      final reply = (response['reply'] as String? ?? '').trim();
      final toolCalls =
          (response['tool_calls'] as List? ?? []).cast<Map<String, dynamic>>();

      if (toolCalls.isEmpty) {
        final menuItems = response['menu_items'] as List? ?? [];
        final deals = response['deals'] as List? ?? [];
        return VoiceCommandResult(
          success: true,
          actionTaken: (menuItems.isNotEmpty || deals.isNotEmpty)
              ? 'menu_inquiry'
              : 'general_reply',
          reply: reply,
          transcript: transcript,
        );
      }

      return await _executeAll(
        toolCalls: toolCalls,
        reply: reply,
        transcript: transcript,
        context: context,
        language: language,
        nav: nav,
        memory: memory,
      );
    } catch (_) {
      return const VoiceCommandResult(success: false);
    }
  }

  // ── English path ──────────────────────────────────────────
  Future<VoiceCommandResult> execute({
    required String transcript,
    required BuildContext context,
    required String sessionId,
    required String language,
    VoiceNavCallbacks? nav,
    ConversationMemory? memory,
  }) async {
    try {
      final response = await ChatService().sendTextMessage(
        sessionId,
        transcript,
        language,
      );
      return executeFromResponse(
        transcript: transcript,
        response: response,
        context: context,
        sessionId: sessionId,
        language: language,
        nav: nav,
        memory: memory,
      );
    } catch (_) {
      return const VoiceCommandResult(success: false);
    }
  }

  // ── Execute ALL tool calls ────────────────────────────────
  Future<VoiceCommandResult> _executeAll({
    required List<Map<String, dynamic>> toolCalls,
    required String reply,
    required String transcript,
    required BuildContext context,
    required String language,
    required VoiceNavCallbacks? nav,
    ConversationMemory? memory,
  }) async {
    String lastAction = '';
    bool navigated = false;
    int addedCount = 0;

    for (final call in toolCalls) {
      final name = (call['name'] as String? ?? '').trim();
      final args = (call['args'] as Map?)
              ?.map((k, v) => MapEntry(k.toString(), v.toString())) ??
          <String, String>{};

      switch (name) {
        case 'add_to_cart':
          final ok = await _addToCart(context, args);
          if (ok) addedCount++;
          lastAction = ok ? 'added_to_cart' : 'item_not_found';
          continue;

        case 'remove_from_cart':
          await _removeFromCart(context, args);
          lastAction = 'removed_from_cart';
          continue;

        case 'change_quantity':
          await _updateQuantity(context, args);
          lastAction = 'quantity_changed';
          continue;

        case 'show_cart':
          nav?.openCart();
          navigated = true;
          lastAction = 'navigated_to_cart';
          break;

        case 'place_order':
          final method = (args['payment_method'] ?? 'COD').toUpperCase();
          nav?.openCheckout(paymentMethod: method);
          navigated = true;
          lastAction = 'navigated_to_checkout';
          break;

        case 'navigate_to':
          final screen = args['screen'] ?? '';
          switch (screen) {
            case 'home':
              nav?.switchTab(0);
              break;

            case 'deals':
              final cuisine = (args['cuisine'] ?? '').trim().isNotEmpty
                  ? args['cuisine']!
                  : ((args['deal_cuisine'] ?? '').trim().isNotEmpty
                      ? args['deal_cuisine']!
                      : null);

              final serving = (args['serving_size'] ?? '').trim().isNotEmpty
                  ? args['serving_size']!
                  : ((args['person_count'] ?? '').trim().isNotEmpty
                      ? args['person_count']!
                      : null);

              final highlightDealId =
                  int.tryParse((args['highlight_deal_id'] ?? '').trim());

              nav?.openDealsWithFilter(
                cuisineFilter: cuisine,
                servingFilter: serving,
                highlightDealId: highlightDealId,
              );
              break;

            case 'profile':
              nav?.switchTab(3);
              break;

            case 'orders':
              nav?.openOrders();
              break;

            case 'favourites':
              nav?.openFavourites();
              break;

            default:
              nav?.switchTab(0);
              break;
          }
          navigated = true;
          lastAction = 'navigated_to_$screen';
          break;

        case 'search_menu':
          final query = (args['query'] ?? '').toLowerCase();
          final cuisine = _detectCuisine(query);
          if (cuisine != null) {
            nav?.openMenuWithFilter(cuisine: cuisine);
          } else {
            nav?.switchTab(1);
          }
          navigated = true;
          lastAction = 'navigated_to_menu';
          break;

        case 'search_deal':
          final cuisine = args['cuisine'] ?? '';
          final personCount = int.tryParse(args['person_count'] ?? '0') ?? 0;

          final dealResult = await _dealService.handleDealSearch(
            cuisine: cuisine,
            personCount: personCount,
            context: context,
            language: language,
            nav: nav,
            memory: memory,
          );

          if (dealResult.suggestCustom &&
              dealResult.customDealQuery.isNotEmpty) {
            return VoiceCommandResult(
              success: true,
              actionTaken: 'custom_deal',
              reply: dealResult.message,
              transcript: dealResult.customDealQuery,
            );
          }

          if (!dealResult.found) {
            final pendingQuery = dealResult.customDealQuery.isNotEmpty
                ? dealResult.customDealQuery
                : 'create ${cuisine.toLowerCase()} deal for $personCount people';

            return VoiceCommandResult(
              success: true,
              actionTaken: 'deal_suggest_custom',
              reply: dealResult.message,
              transcript: pendingQuery,
            );
          }

          navigated = dealResult.navigated;
          lastAction = 'navigated_to_deals';
          break;

        case 'get_order_status':
        case 'order_status':
          lastAction = 'order_status';
          continue;

        case 'manage_favourites':
          final action = args['action'] ?? '';
          if (action == 'show') {
            nav?.openFavourites();
            navigated = true;
          }
          lastAction = 'favourites_$action';
          break;

        case 'get_recommendations':
          nav?.openRecommendations();
          navigated = true;
          lastAction = 'recommendations';
          break;

        case 'create_custom_deal':
          final userQuery = args['user_query']?.isNotEmpty == true
              ? args['user_query']!
              : transcript;
          return VoiceCommandResult(
            success: true,
            actionTaken: 'custom_deal',
            reply: reply,
            transcript: userQuery,
          );

        case 'retrieve_menu_context':
          lastAction = 'menu_inquiry';
          continue;

        case 'weather_upsell':
          lastAction = 'weather_upsell';
          continue;

        default:
          continue;
      }

      if (navigated) break;
    }

    if (lastAction == 'added_to_cart' ||
        lastAction == 'removed_from_cart' ||
        lastAction == 'quantity_changed') {
      if (context.mounted) {
        Provider.of<CartProvider>(context, listen: false).sync();
      }
    }

    return VoiceCommandResult(
      success: true,
      actionTaken: addedCount > 0 ? 'added_to_cart' : lastAction,
      reply: reply,
      transcript: transcript,
      navigated: navigated,
    );
  }

  // ── Cart helpers ──────────────────────────────────────────
  Future<bool> _addToCart(
      BuildContext context, Map<String, String> args) async {
    try {
      final cart = Provider.of<CartProvider>(context, listen: false);
      final cartId = cart.cartId;
      if (cartId == null) return false;
      final itemName = args['item_name'] ?? '';
      final qty = int.tryParse(args['quantity'] ?? '1') ?? 1;
      if (itemName.isEmpty) return false;
      final itemId = await _findItemIdByName(itemName);
      if (itemId == null) return false;
      await CartService.addItem(
          cartId: cartId, itemType: 'menu_item', itemId: itemId, quantity: qty);
      if (context.mounted) {
        Provider.of<CartProvider>(context, listen: false).sync();
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> _removeFromCart(
      BuildContext context, Map<String, String> args) async {
    try {
      final cart = Provider.of<CartProvider>(context, listen: false);
      final cartId = cart.cartId;
      if (cartId == null) return;
      final itemId = await _findItemIdByName(args['item_name'] ?? '');
      if (itemId == null) return;
      await CartService.removeItem(
          cartId: cartId, itemType: 'menu_item', itemId: itemId);
      if (context.mounted) {
        Provider.of<CartProvider>(context, listen: false).sync();
      }
    } catch (_) {}
  }

  Future<void> _updateQuantity(
      BuildContext context, Map<String, String> args) async {
    try {
      final cart = Provider.of<CartProvider>(context, listen: false);
      final cartId = cart.cartId;
      if (cartId == null) return;
      final qty = int.tryParse(args['quantity'] ?? '1') ?? 1;
      final itemId = await _findItemIdByName(args['item_name'] ?? '');
      if (itemId == null) return;
      await CartService.setQuantity(
          cartId: cartId, itemType: 'menu_item', itemId: itemId, quantity: qty);
      if (context.mounted) {
        Provider.of<CartProvider>(context, listen: false).sync();
      }
    } catch (_) {}
  }

  Future<int?> _findItemIdByName(String name) async {
    try {
      final res = await ApiClient.getJson('/menu', auth: false);
      final items = (res['menu'] as List? ?? []).cast<Map<String, dynamic>>();
      final lower = name.toLowerCase();
      for (final item in items) {
        if ((item['item_name'] as String? ?? '').toLowerCase() == lower) {
          return item['item_id'] as int?;
        }
      }
      for (final item in items) {
        final n = (item['item_name'] as String? ?? '').toLowerCase();
        if (n.contains(lower) || lower.contains(n)) {
          return item['item_id'] as int?;
        }
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  String? _detectCuisine(String query) {
    const map = {
      'fast food': 'Fast Food',
      'fast': 'Fast Food',
      'burger': 'Fast Food',
      'chinese': 'Chinese',
      'chow mein': 'Chinese',
      'chowmein': 'Chinese',
      'desi': 'Desi',
      'karahi': 'Desi',
      'biryani': 'Desi',
      'bbq': 'BBQ',
      'tikka': 'BBQ',
      'boti': 'BBQ',
      'drinks': 'Drinks',
      'drink': 'Drinks',
    };
    for (final e in map.entries) {
      if (query.contains(e.key)) return e.value;
    }
    return null;
  }
}

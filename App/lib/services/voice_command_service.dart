import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:provider/provider.dart';

import 'package:khaadim/app_config.dart';
import 'package:khaadim/providers/dine_in_provider.dart';
import 'package:khaadim/services/api_client.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/services/chat_service.dart';
import 'package:khaadim/services/conversation_memory.dart';
import 'package:khaadim/services/dine_in_service.dart';
import 'package:khaadim/services/voice_deal_service.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/widgets/voice_nav_callbacks.dart';
import 'package:khaadim/services/favorites_service.dart';
import 'package:khaadim/providers/favourites_notifier.dart';

double _stringSimilarity(String a, String b) {
  if (a.isEmpty || b.isEmpty) return 0;
  if (a == b) return 1;

  final distance = _levenshteinDistance(a, b);
  final maxLen = a.length > b.length ? a.length : b.length;
  if (maxLen == 0) return 1;

  return 1 - (distance / maxLen);
}

int _levenshteinDistance(String a, String b) {
  if (a == b) return 0;
  if (a.isEmpty) return b.length;
  if (b.isEmpty) return a.length;

  var previous = List<int>.generate(b.length + 1, (i) => i);
  var current = List<int>.filled(b.length + 1, 0);

  for (var i = 0; i < a.length; i++) {
    current[0] = i + 1;
    for (var j = 0; j < b.length; j++) {
      final cost = a.codeUnitAt(i) == b.codeUnitAt(j) ? 0 : 1;
      final insertion = current[j] + 1;
      final deletion = previous[j + 1] + 1;
      final substitution = previous[j] + cost;

      var best = insertion < deletion ? insertion : deletion;
      if (substitution < best) best = substitution;
      current[j + 1] = best;
    }

    final temp = previous;
    previous = current;
    current = temp;
  }

  return previous[b.length];
}

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

/// Callback used by the Kiosk to add items to `DineInProvider` instead of
/// the delivery-mode `CartProvider` (which has no cartId in Kiosk).
typedef DineInAddItemCallback = Future<bool> Function(
  int itemId,
  String itemType,
  String itemName,
  double price,
  int qty,
);

class VoiceCommandService {
  late final VoiceDealService _dealService;
  DineInAddItemCallback? _dineInAddItem;

  // ── Per-command cache ─────────────────────────────────────
  // Populated on the first item lookup within a single voice command and
  // reused for every subsequent item in the same response.  Reset at the
  // start of each executeFromResponse / execute call so data never goes stale
  // across separate voice commands.
  List<Map<String, dynamic>>? _cachedMenuItems;
  List<Map<String, dynamic>>? _cachedDeals;

  static const Map<String, String> _spokenWordNormalization = {
    'hondi': 'handi',
    'handy': 'handi',
    'karai': 'karahi',
    'karhai': 'karahi',
    'tika': 'tikka',
    'boty': 'boti',
    'botiay': 'boti',
  };

  VoiceCommandService({FlutterTts? tts, DineInAddItemCallback? dineInAddItem}) {
    _dealService = VoiceDealService(tts ?? FlutterTts());
    _dineInAddItem = dineInAddItem;
  }

  /// Call this from the Kiosk screen so voice add-to-cart routes through
  /// [DineInProvider.addItem] instead of the delivery CartService.
  void setDineInAddItemCallback(DineInAddItemCallback callback) {
    _dineInAddItem = callback;
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
    // Reset per-command cache so each voice turn starts fresh.
    _cachedMenuItems = null;
    _cachedDeals = null;
    try {
      final reply = (response['reply'] as String? ?? '').trim();
      var toolCalls =
          (response['tool_calls'] as List? ?? []).cast<Map<String, dynamic>>();

      // Payment disambiguation follow-up: after we asked "card or cash?",
      // a bare "cash" / "card" utterance doesn't trigger the backend's
      // settle_payment rule. Promote it here so the guest's one-word
      // response does the right thing.
      toolCalls = _maybePromotePaymentFollowUp(
        context,
        transcript,
        toolCalls,
      );

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

  /// If the provider is awaiting a payment-method choice and the transcript
  /// contains a single "card" or "cash" (or their Urdu forms), inject a
  /// `settle_payment` tool call so the next step runs the right handler.
  /// No-op when there's no pending ask or when a concrete tool call is
  /// already present.
  List<Map<String, dynamic>> _maybePromotePaymentFollowUp(
    BuildContext context,
    String transcript,
    List<Map<String, dynamic>> toolCalls,
  ) {
    if (!_isKioskDineIn(context)) return toolCalls;

    final dineIn = Provider.of<DineInProvider>(context, listen: false);
    if (!dineIn.awaitingPaymentMethod) return toolCalls;

    // If the backend already routed to settle_payment we're done.
    if (toolCalls.any((c) {
      return (c['name'] as String? ?? '').toLowerCase() == 'settle_payment';
    })) {
      return toolCalls;
    }

    final raw = transcript.toLowerCase();
    String? method;
    // Cash keywords (English / Roman-Urdu / Urdu script).
    const cashKeys = [
      'cash', 'naqad', 'naqd', 'نقد', 'کیش', 'کیاش',
    ];
    const cardKeys = [
      'card', 'kaard', 'credit', 'debit', 'کارڈ', 'گاڈ',
    ];
    for (final k in cashKeys) {
      if (raw.contains(k) || transcript.contains(k)) {
        method = 'cash';
        break;
      }
    }
    if (method == null) {
      for (final k in cardKeys) {
        if (raw.contains(k) || transcript.contains(k)) {
          method = 'card';
          break;
        }
      }
    }

    if (method == null) return toolCalls;

    return <Map<String, dynamic>>[
      {
        'name': 'settle_payment',
        'args': {'payment_method': method},
      },
      ...toolCalls,
    ];
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
    // We keep `effectiveReply` as the backend's rich reply by default
    // (e.g. "Added Biryani and Zinger Burger to your cart"). Only fall
    // back to a localised generic string when the backend sent us
    // nothing at all — otherwise TTS would get the SAME sentence on
    // every add-to-cart and the duplicate-guard silences it.
    String effectiveReply = reply.trim();
    int addedCount = 0;
    int failedCount = 0;
    final List<String> addedNames = <String>[];

    for (final call in toolCalls) {
      final name = (call['name'] as String? ?? '').trim();
      final args = (call['args'] as Map?)
              ?.map((k, v) => MapEntry(k.toString(), v.toString())) ??
          <String, String>{};

      switch (name) {
        case 'add_to_cart':
          final ok = await _addToCart(context, args);
          if (ok) {
            addedCount++;
            final itemName = (args['item_name'] ?? '').trim();
            if (itemName.isNotEmpty) addedNames.add(itemName);
          } else {
            failedCount++;
          }
          lastAction = ok ? 'added_to_cart' : 'item_not_found';
          // Only override the reply if the backend didn't already give us
          // one AND the cart operation actually failed (user needs to know).
          if (effectiveReply.isEmpty && !ok) {
            effectiveReply = _localized(
              language,
              urdu: 'آئٹم نہیں ملا۔',
              english: 'Item not found.',
            );
          }
          continue;

        case 'remove_from_cart':
          final removed = await _removeFromCart(context, args);
          lastAction = removed ? 'removed_from_cart' : 'item_not_found';
          // Only supply a fallback when backend didn't send a reply. The
          // item name in the fallback keeps each utterance unique so TTS
          // dedup doesn't silence repeated removes.
          if (effectiveReply.isEmpty) {
            final itemName = (args['item_name'] ?? '').trim();
            effectiveReply = removed
                ? (language.toLowerCase() == 'ur'
                    ? (itemName.isEmpty
                        ? 'آئٹم کارٹ سے ہٹا دیا۔'
                        : '$itemName کارٹ سے ہٹا دیا۔')
                    : (itemName.isEmpty
                        ? 'Item removed from cart.'
                        : 'Removed $itemName from your cart.'))
                : _localized(
                    language,
                    urdu: 'آئٹم کارٹ میں نہیں ملا۔',
                    english: 'Item was not found in cart.',
                  );
          }
          continue;

        case 'change_quantity':
          final updated = await _updateQuantity(context, args);
          lastAction = updated ? 'quantity_changed' : 'item_not_found';
          if (effectiveReply.isEmpty) {
            final itemName = (args['item_name'] ?? '').trim();
            final qty = (args['quantity'] ?? '').trim();
            effectiveReply = updated
                ? (language.toLowerCase() == 'ur'
                    ? (itemName.isEmpty
                        ? 'کارٹ اپڈیٹ کر دی گئی۔'
                        : '$itemName کی مقدار $qty کر دی گئی۔')
                    : (itemName.isEmpty
                        ? 'Cart quantity updated.'
                        : 'Set $itemName quantity to $qty.'))
                : _localized(
                    language,
                    urdu: 'آئٹم کارٹ میں نہیں ملا۔',
                    english: 'Item was not found in cart.',
                  );
          }
          continue;

        case 'show_cart':
          nav?.openCart();
          navigated = true;
          lastAction = 'navigated_to_cart';
          break;

        case 'place_order':
          if (_isKioskDineIn(context)) {
            effectiveReply = await _placeDineInOrder(context, language);
            lastAction = 'order_placed';
            continue;
          }
          final method = (args['payment_method'] ?? 'COD').toUpperCase();
          nav?.openCheckout(paymentMethod: method);
          navigated = true;
          lastAction = 'navigated_to_checkout';
          effectiveReply = _localized(
            language,
            urdu: 'چیک آؤٹ اسکرین کھول رہا ہوں۔',
            english: 'Opening checkout.',
          );
          break;

        case 'call_waiter':
          effectiveReply = await _callWaiter(context, args, language);
          lastAction = 'waiter_called';
          continue;

        case 'settle_payment':
        case 'select_payment_method':
          effectiveReply = await _settlePayment(context, args, language);
          lastAction = 'payment_settled';
          continue;

        case 'navigate_to':
          final screen = args['screen'] ?? '';
          switch (screen) {
            case 'home':
              nav?.switchTab(0);
              break;

            case 'deals':
              var cuisine = (args['cuisine'] ?? '').trim().isNotEmpty
                  ? args['cuisine']!
                  : ((args['deal_cuisine'] ?? '').trim().isNotEmpty
                      ? args['deal_cuisine']!
                      : null);

              // Fall back to detecting cuisine from the raw transcript so
              // Urdu utterances like "بی بی کیو کی ڈیل دکھاؤ" still seed
              // the BBQ chip on the deals screen.
              if ((cuisine == null || cuisine.trim().isEmpty) &&
                  transcript.isNotEmpty) {
                cuisine = _detectCuisine(transcript);
              }

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
          final rawQuery = (args['query'] ?? '').toString();
          final query = rawQuery.toLowerCase();

          // Backend may forward explicit cuisine/category args alongside the
          // free-text query. Prefer those when available, otherwise detect
          // from the raw utterance (English, Roman-Urdu, or Urdu script).
          final explicitCuisine = (args['cuisine'] ?? '').trim();
          final explicitCategory = (args['category'] ?? '').trim();

          final cuisine = explicitCuisine.isNotEmpty
              ? explicitCuisine
              : (_detectCuisine(query) ??
                  _detectCuisine(rawQuery) ??
                  _detectCuisine(transcript));
          final category = explicitCategory.isNotEmpty
              ? explicitCategory
              : (_detectCategory(query) ??
                  _detectCategory(rawQuery) ??
                  _detectCategory(transcript));

          if (cuisine != null || category != null) {
            nav?.openMenuWithFilter(
              cuisine: cuisine,
              category: category,
            );
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
          effectiveReply = await _getOrderStatusReply(context, language);
          lastAction = 'order_status';
          continue;

        case 'manage_favourites':
          final action = args['action'] ?? '';
          if (action == 'show') {
            nav?.openFavourites();
            navigated = true;
          } else if (action == 'add' || action == 'remove') {
            final itemName = args['item_name'] ?? '';
            final itemIdStr = args['item_id'] ?? '';
            final itemType = args['item_type'] ?? '';

            if (itemIdStr.isNotEmpty && itemType.isNotEmpty) {
              final itemId = int.tryParse(itemIdStr);
              if (itemId != null) {
                try {
                  int? reqItemId;
                  int? reqDealId;
                  if (itemType == 'menu_item') reqItemId = itemId;
                  else if (itemType == 'deal') reqDealId = itemId;

                  final res = await FavouritesService.toggleFavourite(
                    itemId: reqItemId,
                    dealId: reqDealId,
                  );

                  // Determine actual action from server response (toggle
                  // means it may have added OR removed based on current state).
                  final serverAction = (res['action'] as String? ?? action);
                  final wasAdded = serverAction == 'added';

                  // Notify notifier so heart icons update without a reload.
                  if (itemType == 'menu_item') {
                    FavouritesNotifier.instance.updateItem(itemId, added: wasAdded);
                  } else if (itemType == 'deal') {
                    FavouritesNotifier.instance.updateDeal(itemId, added: wasAdded);
                  }

                  if (effectiveReply.isEmpty) {
                    if (wasAdded) {
                      effectiveReply = language.toLowerCase() == 'ur'
                          ? '${itemName.isNotEmpty ? itemName : "آئٹم"} فیورٹ میں شامل کر دیا گیا۔'
                          : 'Added ${itemName.isNotEmpty ? itemName : "item"} to favourites.';
                    } else {
                      effectiveReply = language.toLowerCase() == 'ur'
                          ? '${itemName.isNotEmpty ? itemName : "آئٹم"} فیورٹ سے ہٹا دیا گیا۔'
                          : 'Removed ${itemName.isNotEmpty ? itemName : "item"} from favourites.';
                    }
                  }
                } catch (_) {
                  if (effectiveReply.isEmpty) {
                    effectiveReply = _localized(language, urdu: 'ایک مسئلہ پیش آیا۔', english: 'An error occurred.');
                  }
                }
              }
            } else {
              if (effectiveReply.isEmpty) {
                effectiveReply = _localized(language, urdu: 'آئٹم نہیں ملا۔', english: 'Item not found.');
              }
            }
          }
          lastAction = 'favourites_$action';
          break;

        case 'get_recommendations':
          if (_isKioskDineIn(context)) {
            effectiveReply = await _getTopSellerSuggestions(context, language);
            lastAction = 'recommendations';
            continue;
          }
          final recommendationReply = await ChatService().getVoiceRecommendations(language: language);
          if (recommendationReply.isNotEmpty) {
            effectiveReply = recommendationReply;
          } else if (effectiveReply.trim().isEmpty) {
            effectiveReply = _localized(
              language,
              urdu: 'سفارشات دکھا رہا ہوں۔',
              english: 'Opening recommendations.',
            );
          }
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
        case 'describe_item':
          // Info-intent (e.g. "spring rolls ke baray mein batao"). The
          // backend already baked the full Urdu/English description into
          // `reply`; we just need to make sure the handler routes it to
          // TTS by tagging the action as a menu inquiry.
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
      if (!AppConfig.isKiosk && context.mounted) {
        Provider.of<CartProvider>(context, listen: false).sync();
      }
    }

    // BUG-FIX: When items were actually added, ALWAYS build a clean
    // confirmation reply — never let a search-result string (e.g.
    // "یہ ملتے جلتے آئٹمز ہیں") leak through from the backend reply.
    // The per-item list keeps each utterance unique so the TTS dedup
    // guard doesn't silence consecutive add-to-cart confirmations.
    if (addedCount > 0) {
      final uniqueNames = <String>[];
      for (final n in addedNames) {
        if (!uniqueNames.contains(n)) uniqueNames.add(n);
      }
      if (language.toLowerCase() == 'ur') {
        if (uniqueNames.length == 1) {
          effectiveReply = '${uniqueNames[0]} کارٹ میں شامل کر دیا۔';
        } else if (uniqueNames.length == 2) {
          effectiveReply =
              '${uniqueNames[0]} اور ${uniqueNames[1]} کارٹ میں شامل کر دیے۔';
        } else if (uniqueNames.isNotEmpty) {
          final head =
              uniqueNames.sublist(0, uniqueNames.length - 1).join('، ');
          effectiveReply = '$head اور ${uniqueNames.last} کارٹ میں شامل کر دیے۔';
        } else {
          effectiveReply = 'آئٹم کارٹ میں شامل کر دیا۔';
        }
      } else {
        if (uniqueNames.length == 1) {
          effectiveReply = 'Added ${uniqueNames[0]} to your cart.';
        } else if (uniqueNames.length == 2) {
          effectiveReply =
              'Added ${uniqueNames[0]} and ${uniqueNames[1]} to your cart.';
        } else if (uniqueNames.isNotEmpty) {
          final head =
              uniqueNames.sublist(0, uniqueNames.length - 1).join(', ');
          effectiveReply =
              'Added $head and ${uniqueNames.last} to your cart.';
        } else {
          effectiveReply = 'Item added to cart.';
        }
      }
    }

    return VoiceCommandResult(
      success: true,
      actionTaken: addedCount > 0 ? 'added_to_cart' : lastAction,
      reply: effectiveReply,
      transcript: transcript,
      navigated: navigated,
    );
  }

  bool _isKioskDineIn(BuildContext context) {
    if (!AppConfig.isKiosk) return false;
    final dineIn = Provider.of<DineInProvider>(context, listen: false);
    return (dineIn.sessionId ?? '').trim().isNotEmpty || _dineInAddItem != null;
  }

  String _localized(
    String language, {
    required String urdu,
    required String english,
  }) {
    return language.toLowerCase() == 'ur' ? urdu : english;
  }

  Future<String> _placeDineInOrder(BuildContext context, String language) async {
    final dineIn = Provider.of<DineInProvider>(context, listen: false);
    final sessionId = (dineIn.sessionId ?? '').trim();

    if (sessionId.isEmpty) {
      return _localized(
        language,
        urdu: 'فعال ڈائن اِن سیشن نہیں ملا۔',
        english: 'No active dine-in session found.',
      );
    }

    final payloadItems = _buildDineInOrderPayload(dineIn.currentOrderItems);
    if (payloadItems.isEmpty) {
      return _localized(
        language,
        urdu: 'کارٹ خالی ہے۔ پہلے آئٹمز شامل کریں۔',
        english: 'Your cart is empty. Please add items first.',
      );
    }

    try {
      final res = await DineInService().placeOrder(sessionId, payloadItems);
      final roundRaw = res['round_number'];
      final roundNumber = roundRaw is int
          ? roundRaw
          : int.tryParse((roundRaw ?? '').toString()) ?? 0;
      dineIn.clearOrder();

      if (language.toLowerCase() == 'ur') {
        return roundNumber > 0
            ? 'آرڈر کچن کو بھیج دیا گیا۔ راؤنڈ $roundNumber شروع ہو گیا ہے۔'
            : 'آرڈر کچن کو بھیج دیا گیا۔';
      }

      return roundNumber > 0
          ? 'Order sent to kitchen. Round $roundNumber has started.'
          : 'Order sent to kitchen.';
    } catch (e) {
      final message = e.toString().replaceFirst('Exception: ', '').trim();
      if (message.isNotEmpty) return message;
      return _localized(
        language,
        urdu: 'آرڈر بھیجنے میں مسئلہ آیا۔ دوبارہ کوشش کریں۔',
        english: 'Could not place the order. Please try again.',
      );
    }
  }

  List<Map<String, dynamic>> _buildDineInOrderPayload(
    List<Map<String, dynamic>> currentItems,
  ) {
    final Map<String, Map<String, dynamic>> aggregated =
        <String, Map<String, dynamic>>{};

    void addNormalized(String rawType, int rawId, int rawQuantity) {
      if (rawId <= 0 || rawQuantity <= 0) return;
      final normalizedType = rawType == 'deal' ? 'deal' : 'menu_item';
      final key = '$normalizedType:$rawId';
      final existing = aggregated[key];

      if (existing == null) {
        aggregated[key] = {
          'item_type': normalizedType,
          'item_id': rawId,
          'quantity': rawQuantity,
        };
        return;
      }

      final existingQty = (existing['quantity'] as int?) ?? 0;
      existing['quantity'] = existingQty + rawQuantity;
    }

    for (final item in currentItems) {
      final itemType = (item['item_type'] ?? 'menu_item').toString();
      final parentQty = _asInt(item['quantity']) ?? 1;

      if (itemType == 'custom_deal') {
        final bundle = item['bundle_items'];
        if (bundle is! List) continue;

        for (final raw in bundle) {
          if (raw is! Map) continue;
          final rawItemType = (raw['item_type'] ?? 'menu_item').toString();
          final itemId = _asInt(raw['item_id']) ?? 0;
          final itemQty = _asInt(raw['quantity']) ?? 1;
          addNormalized(rawItemType, itemId, itemQty * parentQty);
        }
        continue;
      }

      final itemId = _asInt(item['item_id']) ?? 0;
      addNormalized(itemType, itemId, parentQty);
    }

    return aggregated.values.toList();
  }

  Future<String> _callWaiter(
    BuildContext context,
    Map<String, String> args,
    String language,
  ) async {
    if (!_isKioskDineIn(context)) {
      return _localized(
        language,
        urdu: 'ویٹر کال صرف ڈائن اِن سیشن میں دستیاب ہے۔',
        english: 'Waiter call is available in dine-in sessions only.',
      );
    }

    final dineIn = Provider.of<DineInProvider>(context, listen: false);
    final sessionId = (dineIn.sessionId ?? '').trim();
    if (sessionId.isEmpty) {
      return _localized(
        language,
        urdu: 'فعال سیشن موجود نہیں۔',
        english: 'No active dine-in session found.',
      );
    }

    final forCash = (args['for_cash_payment'] ?? '').toLowerCase() == 'true';

    try {
      // Go through the provider so the shared waiter-call state machine
      // (notified → acknowledged → idle) and the status polling kick in,
      // driving the same UI feedback as the manual "CALL WAITER" button.
      final res = await dineIn.notifyWaiter(forCashPayment: forCash);

      final msg = (res['message'] ?? '').toString().trim();
      if (msg.isNotEmpty) return msg;
      return _localized(
        language,
        urdu: 'ویٹر کو اطلاع دے دی گئی ہے۔',
        english: 'Waiter has been notified.',
      );
    } catch (e) {
      final message = e.toString().replaceFirst('Exception: ', '').trim();
      if (message.isNotEmpty) return message;
      return _localized(
        language,
        urdu: 'ویٹر کال نہیں ہو سکی۔',
        english: 'Could not notify waiter.',
      );
    }
  }

  /// Voice-driven payment.
  ///
  /// Three paths depending on the `payment_method` arg:
  ///  • `card`  → navigate to My Table with an auto-payment intent; the
  ///              payment screen runs the exact same handler as the manual
  ///              "Pay by Card" tap (confirm dialog, add-card fallback,
  ///              settlement popup, session reset → kiosk home).
  ///  • `cash`  → same navigation; payment screen runs the cash handler
  ///              (confirm → notify kitchen → session auto-ends after
  ///              kitchen confirmation).
  ///  • `ask`   → ask "card or cash?" and remember the pending prompt on
  ///              `DineInProvider`. The follow-up utterance's method wins.
  ///
  /// Eligibility messaging is delegated to the payment screen (it shows
  /// the same SnackBars it would for a manual tap) so voice and manual
  /// UX stay in lockstep.
  Future<String> _settlePayment(
    BuildContext context,
    Map<String, String> args,
    String language,
  ) async {
    if (!_isKioskDineIn(context)) {
      return _localized(
        language,
        urdu: 'ادائیگی صرف ڈائن اِن سیشن میں دستیاب ہے۔',
        english: 'Payment is available in dine-in sessions only.',
      );
    }

    final dineIn = Provider.of<DineInProvider>(context, listen: false);
    final sessionId = (dineIn.sessionId ?? '').trim();
    if (sessionId.isEmpty) {
      return _localized(
        language,
        urdu: 'فعال سیشن نہیں ملا۔',
        english: 'No active session found.',
      );
    }

    final rawMethod = (args['payment_method'] ?? '').trim().toLowerCase();
    String method;
    if (rawMethod.contains('cash')) {
      method = 'cash';
    } else if (rawMethod.contains('card')) {
      method = 'card';
    } else if (rawMethod == 'ask') {
      method = 'ask';
    } else {
      method = 'ask';
    }

    if (method == 'ask') {
      // Mark the provider so the next utterance's "card"/"cash" keyword
      // short-circuits straight back into this handler.
      dineIn.setAwaitingPaymentMethod();
      return _localized(
        language,
        urdu: 'کارڈ سے ادائیگی کرنی ہے یا کیش سے؟',
        english: 'Would you like to pay by card or by cash?',
      );
    }

    // Consume any pending disambiguation so we don't double-fire.
    dineIn.clearAwaitingPaymentMethod();

    // Sanity: eligibility is re-checked inside the payment screen, but we
    // can bail out early with a specific voice reply when there's nothing
    // to pay for — no point navigating.
    try {
      final rounds = await DineInService().fetchSessionOrders(
        sessionId,
        token: dineIn.token,
      );
      if (rounds.isEmpty) {
        return _localized(
          language,
          urdu: 'ابھی کوئی آرڈر موجود نہیں، پہلے آرڈر دیں۔',
          english: 'No orders placed yet. Please place an order first.',
        );
      }

      bool parseBool(dynamic v) {
        if (v is bool) return v;
        final s = (v ?? '').toString().toLowerCase();
        return s == 'paid' || s == 'settled' || s == 'true';
      }

      final allPaid = rounds.every((r) {
        final paidFlag = r['is_paid'] ?? r['paid'];
        if (paidFlag != null) return parseBool(paidFlag);
        final paymentStatus = (r['payment_status'] ?? '').toString().toLowerCase();
        if (paymentStatus == 'paid' || paymentStatus == 'settled') return true;
        final status = (r['status'] ?? '').toString().toLowerCase();
        return status == 'paid' || status == 'settled';
      });
      if (allPaid) {
        return _localized(
          language,
          urdu: 'تمام راؤنڈز کی ادائیگی ہو چکی ہے۔',
          english: 'All rounds are already paid.',
        );
      }

      final allCompleted = rounds.every((r) {
        final ks = (r['kitchen_status'] ?? r['status'] ?? '')
            .toString()
            .toLowerCase();
        return ks == 'completed' || ks == 'served';
      });
      if (!allCompleted) {
        return _localized(
          language,
          urdu: 'پہلے تمام راؤنڈز کا کچن میں مکمل ہونا ضروری ہے، پھر ادائیگی ہو سکے گی۔',
          english:
              'Payment unlocks after all rounds are completed in the kitchen.',
        );
      }
    } catch (_) {
      // Non-fatal: if the eligibility check fails we still navigate so the
      // payment screen can render its own error state.
    }

    if (!context.mounted) {
      return _localized(
        language,
        urdu: 'ادائیگی کی اسکرین کھول رہا ہوں۔',
        english: 'Opening the payment screen.',
      );
    }

    // Navigate to My Table with the auto-payment intent. MyTableScreen reads
    // the arg, fetches rounds, then pushes the payment screen which runs the
    // matching handler automatically — identical behaviour to a manual tap.
    Navigator.of(context).pushNamed(
      '/kiosk-table',
      arguments: <String, dynamic>{'auto_payment': method},
    );

    if (method == 'cash') {
      return _localized(
        language,
        urdu: 'کیش ادائیگی کے لیے کچن کو اطلاع دے رہا ہوں۔',
        english: 'Notifying the kitchen for cash payment.',
      );
    }
    return _localized(
      language,
      urdu: 'کارڈ ادائیگی کی اسکرین کھول رہا ہوں۔',
      english: 'Opening the card payment screen.',
    );
  }

  Future<String> _getOrderStatusReply(
    BuildContext context,
    String language,
  ) async {
    if (!_isKioskDineIn(context)) {
      final status = await ChatService().getOrderStatus();
      return status.trim().isEmpty
          ? _localized(
              language,
              urdu: 'آرڈر اسٹیٹس اس وقت دستیاب نہیں۔',
              english: 'Order status is not available right now.',
            )
          : status;
    }

    final dineIn = Provider.of<DineInProvider>(context, listen: false);
    final sessionId = (dineIn.sessionId ?? '').trim();
    if (sessionId.isEmpty) {
      return _localized(
        language,
        urdu: 'فعال سیشن موجود نہیں۔',
        english: 'No active session found.',
      );
    }

    try {
      final orders = await DineInService().fetchSessionOrders(
        sessionId,
        token: dineIn.token,
      );
      if (orders.isEmpty) {
        return _localized(
          language,
          urdu: 'ابھی کوئی آرڈر موجود نہیں۔',
          english: 'No dine-in orders found yet.',
        );
      }

      final latest = orders.last;
      final orderId = _asInt(latest['order_id']) ?? 0;
      var status = (latest['kitchen_status'] ?? latest['status'] ?? 'confirmed')
          .toString()
          .toLowerCase();
      var eta = _asInt(latest['estimated_prep_time_minutes']) ?? 0;

      if (orderId > 0) {
        try {
          final tracking = await DineInService().fetchSessionOrderTracking(
            sessionId,
            orderId,
            token: dineIn.token,
          );
          status =
              (tracking['status'] ?? status).toString().toLowerCase();
          eta = _asInt(tracking['estimated_prep_time_minutes']) ?? eta;
        } catch (_) {
          // Keep session-order snapshot if tracking call fails.
        }
      }

      if (language.toLowerCase() == 'ur') {
        final etaPart = eta > 0 ? ' اندازاً $eta منٹ باقی ہیں۔' : ' وقت جلد اپڈیٹ ہوگا۔';
        return 'آخری آرڈر کی حالت: ${status.toUpperCase()}۔$etaPart';
      }

      final etaPart = eta > 0
          ? ' Estimated time left: $eta minutes.'
          : ' Estimated time will update shortly.';
      return 'Latest order status: ${status.toUpperCase()}.$etaPart';
    } catch (e) {
      final message = e.toString().replaceFirst('Exception: ', '').trim();
      if (message.isNotEmpty) return message;
      return _localized(
        language,
        urdu: 'آرڈر اسٹیٹس حاصل نہیں ہو سکا۔',
        english: 'Could not fetch order status.',
      );
    }
  }

  Future<String> _getTopSellerSuggestions(
    BuildContext context,
    String language,
  ) async {
    if (!_isKioskDineIn(context)) {
      return ChatService().getVoiceRecommendations(language: language);
    }

    final dineIn = Provider.of<DineInProvider>(context, listen: false);
    try {
      final data = await DineInService().fetchTopSellers(token: dineIn.token);
      final menuRaw = (data['top_menu_items'] as List? ?? []).cast<dynamic>();
      final dealsRaw = (data['top_deals'] as List? ?? []).cast<dynamic>();

      final topMenu = menuRaw
          .whereType<Map>()
          .map((e) => (e['item_name'] ?? '').toString().trim())
          .where((name) => name.isNotEmpty)
          .take(2)
          .toList();

      final topDeals = dealsRaw
          .whereType<Map>()
          .map((e) => (e['item_name'] ?? e['deal_name'] ?? '').toString().trim())
          .where((name) => name.isNotEmpty)
          .take(1)
          .toList();

      if (topMenu.isEmpty && topDeals.isEmpty) {
        return _localized(
          language,
          urdu: 'اس وقت ٹاپ سفارشات دستیاب نہیں۔',
          english: 'Top recommendations are not available right now.',
        );
      }

      if (language.toLowerCase() == 'ur') {
        final menuPart = topMenu.isNotEmpty ? 'ٹاپ آئٹمز: ${topMenu.join('، ')}۔ ' : '';
        final dealPart = topDeals.isNotEmpty ? 'ٹاپ ڈیل: ${topDeals.join('، ')}۔' : '';
        return '$menuPart$dealPart'.trim();
      }

      final menuPart = topMenu.isNotEmpty ? 'Top items: ${topMenu.join(', ')}. ' : '';
      final dealPart = topDeals.isNotEmpty ? 'Top deal: ${topDeals.join(', ')}.' : '';
      return '$menuPart$dealPart'.trim();
    } catch (_) {
      return _localized(
        language,
        urdu: 'سفارشات حاصل نہیں ہو سکیں۔',
        english: 'Could not fetch recommendations right now.',
      );
    }
  }

  int? _asInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse((value ?? '').toString());
  }

  // ── Cart helpers ──────────────────────────────────────────

  /// Lazily fetch and cache the full menu list for this voice command cycle.
  Future<List<Map<String, dynamic>>> _getMenuCache() async {
    if (_cachedMenuItems != null) return _cachedMenuItems!;
    try {
      final res = await ApiClient.getJson('/menu', auth: false);
      _cachedMenuItems =
          (res['menu'] as List? ?? []).cast<Map<String, dynamic>>();
    } catch (_) {
      _cachedMenuItems = [];
    }
    return _cachedMenuItems!;
  }

  /// Lazily fetch and cache the full deals list for this voice command cycle.
  Future<List<Map<String, dynamic>>> _getDealsCache() async {
    if (_cachedDeals != null) return _cachedDeals!;
    try {
      final res = await ApiClient.getJson('/deals', auth: false);
      _cachedDeals = (res['deals'] as List? ?? [])
          .whereType<Map>()
          .map((d) => Map<String, dynamic>.from(d))
          .toList();
    } catch (_) {
      _cachedDeals = [];
    }
    return _cachedDeals!;
  }

  Future<bool> _addToCart(
      BuildContext context, Map<String, String> args) async {
    try {
      final itemName = args['item_name'] ?? '';
      final qty = int.tryParse(args['quantity'] ?? '1') ?? 1;
      if (itemName.isEmpty) return false;

      // ── Kiosk / Dine-In path ─────────────────────────────
      // CartProvider has no cartId in Kiosk because no user logs in.
      // Use the injected DineInProvider callback instead.
      if (_dineInAddItem != null) {
        final menuItem = await _findItemDetailsByName(itemName);
        if (menuItem != null) {
          final itemId = (menuItem['item_id'] as num?)?.toInt() ?? 0;
          if (itemId > 0) {
            final resolvedName =
                (menuItem['item_name'] as String? ?? itemName);
            final price =
                (menuItem['item_price'] as num?)?.toDouble() ?? 0.0;
            return await _dineInAddItem!(
              itemId,
              'menu_item',
              resolvedName,
              price,
              qty,
            );
          }
        }

        final dealItem = await _findDealDetailsByName(itemName);
        if (dealItem != null) {
          final dealId = _asInt(dealItem['deal_id']) ?? 0;
          if (dealId > 0) {
            final resolvedName =
                (dealItem['deal_name'] as String? ?? itemName);
            final price =
                (dealItem['deal_price'] as num?)?.toDouble() ?? 0.0;
            return await _dineInAddItem!(
              dealId,
              'deal',
              resolvedName,
              price,
              qty,
            );
          }
        }
        return false;
      }

      // ── Delivery / Customer path ──────────────────────────
      final cart = Provider.of<CartProvider>(context, listen: false);

      // BUG-FIX 2: auto-initialize cart when cartId is null so the first
      // voice add-to-cart doesn't silently fail on a fresh session.
      String? cartId = cart.cartId;
      if (cartId == null) {
        try {
          final freshCart = await CartService.getOrCreateActiveCart();
          cartId = (freshCart['cart_id'] ?? '').toString();
          if (cartId.isEmpty) cartId = null;
          // Keep provider in sync so the badge updates.
          if (cartId != null && context.mounted) {
            Provider.of<CartProvider>(context, listen: false).sync();
          }
        } catch (_) {
          cartId = null;
        }
      }
      if (cartId == null) return false;

      // BUG-FIX 4: use pre-resolved item_id from backend when available,
      // skipping the second /menu HTTP lookup entirely.
      final preResolvedId = int.tryParse(args['item_id'] ?? '');
      final preResolvedType = (args['item_type'] ?? '').trim();
      if (preResolvedId != null &&
          preResolvedId > 0 &&
          preResolvedType.isNotEmpty) {
        await CartService.addItem(
          cartId: cartId,
          itemType: preResolvedType,
          itemId: preResolvedId,
          quantity: qty,
        );
        if (context.mounted) {
          Provider.of<CartProvider>(context, listen: false).sync();
        }
        return true;
      }

      // Fallback: resolve by name via cached menu/deals list (BUG-FIX 3).
      final itemId = await _findItemIdByName(itemName);
      if (itemId != null) {
        await CartService.addItem(
          cartId: cartId,
          itemType: 'menu_item',
          itemId: itemId,
          quantity: qty,
        );
      } else {
        final deal = await _findDealDetailsByName(itemName);
        final dealId = _asInt(deal?['deal_id']) ?? 0;
        if (dealId <= 0) return false;
        await CartService.addItem(
          cartId: cartId,
          itemType: 'deal',
          itemId: dealId,
          quantity: qty,
        );
      }
      if (context.mounted) {
        Provider.of<CartProvider>(context, listen: false).sync();
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Returns the full menu-item map (including price and name) for a given
  /// display name, using an exact match then fuzzy fallback.
  /// Uses the per-command cache so only one /menu HTTP call is made per
  /// voice command regardless of how many items are in the response.
  Future<Map<String, dynamic>?> _findItemDetailsByName(String name) async {
    try {
      // BUG-FIX 3: use shared cache instead of a fresh HTTP call each time.
      final items = await _getMenuCache();
      final lower = name.toLowerCase().trim();
      final normalizedTarget = _normalizeSpokenName(lower);

      // 1. Exact match.
      for (final item in items) {
        final rawName = (item['item_name'] as String? ?? '').toLowerCase();
        final normalizedItem = _normalizeSpokenName(rawName);
        if (rawName == lower || normalizedItem == normalizedTarget) {
          return item;
        }
      }

      // 2. Substring containment.
      for (final item in items) {
        final rawName = (item['item_name'] as String? ?? '').toLowerCase();
        final normalizedItem = _normalizeSpokenName(rawName);
        if (rawName.contains(lower) ||
            lower.contains(rawName) ||
            normalizedItem.contains(normalizedTarget) ||
            normalizedTarget.contains(normalizedItem)) {
          return item;
        }
      }

      // 3. Fuzzy similarity (conservative threshold to avoid wrong items).
      Map<String, dynamic>? bestItem;
      var bestScore = 0.0;
      for (final item in items) {
        final rawName = (item['item_name'] as String? ?? '').toLowerCase();
        final normalizedItem = _normalizeSpokenName(rawName);
        if (normalizedItem.isEmpty) continue;
        final score = _stringSimilarity(normalizedTarget, normalizedItem);
        if (score > bestScore) {
          bestScore = score;
          bestItem = item;
        }
      }
      if (bestItem != null && bestScore >= 0.78) return bestItem;

      return null;
    } catch (_) {
      return null;
    }
  }

  String _normalizeSpokenName(String value) {
    var normalized = value.toLowerCase();
    normalized = normalized.replaceAll(RegExp(r'[^a-z0-9\s]'), ' ');
    normalized = normalized.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (normalized.isEmpty) return normalized;

    final words = normalized
        .split(' ')
        .map((word) => _spokenWordNormalization[word] ?? word)
        .toList();
    return words.join(' ');
  }

  Future<Map<String, dynamic>?> _findDealDetailsByName(String name) async {
    try {
      // BUG-FIX 3: use shared cache instead of a fresh HTTP call each time.
      final deals = await _getDealsCache();
      final lower = name.toLowerCase().trim();

      // 1. Exact match.
      for (final deal in deals) {
        final dealName = (deal['deal_name'] as String? ?? '').toLowerCase();
        if (dealName == lower) return deal;
      }

      // 2. BUG-FIX 5: fuzzy similarity before substring — prevents "BBQ Deal"
      //    from incorrectly matching "BBQ Family Deal" because the shorter
      //    string is a substring of the longer one.
      Map<String, dynamic>? bestDeal;
      double bestScore = 0.0;
      for (final deal in deals) {
        final dealName = (deal['deal_name'] as String? ?? '').toLowerCase();
        if (dealName.isEmpty) continue;
        final score = _stringSimilarity(lower, dealName);
        if (score > bestScore) {
          bestScore = score;
          bestDeal = deal;
        }
      }
      // Use similarity result only when confidence is reasonable.
      if (bestDeal != null && bestScore >= 0.72) return bestDeal;

      // 3. Substring fallback (last resort, most permissive).
      for (final deal in deals) {
        final dealName = (deal['deal_name'] as String? ?? '').toLowerCase();
        if (dealName.contains(lower) || lower.contains(dealName)) {
          return deal;
        }
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  Future<bool> _removeFromCart(
      BuildContext context, Map<String, String> args) async {
    try {
      if (_isKioskDineIn(context)) {
        final dineIn = Provider.of<DineInProvider>(context, listen: false);
        final target =
            _findDineInItemByName(dineIn.currentOrderItems, args['item_name'] ?? '');
        if (target == null) return false;
        final itemId = _asInt(target['item_id']) ?? 0;
        if (itemId <= 0) return false;
        final itemType = (target['item_type'] ?? 'menu_item').toString();
        dineIn.removeItem(itemId, itemType);
        return true;
      }

      final cart = Provider.of<CartProvider>(context, listen: false);
      final cartId = cart.cartId;
      if (cartId == null) return false;
      final requestedName = args['item_name'] ?? '';

      final itemId = await _findItemIdByName(requestedName);
      if (itemId != null) {
        await CartService.removeItem(
          cartId: cartId,
          itemType: 'menu_item',
          itemId: itemId,
        );
      } else {
        final deal = await _findDealDetailsByName(requestedName);
        final dealId = _asInt(deal?['deal_id']) ?? 0;
        if (dealId <= 0) return false;
        await CartService.removeItem(
          cartId: cartId,
          itemType: 'deal',
          itemId: dealId,
        );
      }

      if (context.mounted) {
        Provider.of<CartProvider>(context, listen: false).sync();
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> _updateQuantity(
      BuildContext context, Map<String, String> args) async {
    try {
      final qty = int.tryParse(args['quantity'] ?? '1') ?? 1;

      if (_isKioskDineIn(context)) {
        final dineIn = Provider.of<DineInProvider>(context, listen: false);
        final target =
            _findDineInItemByName(dineIn.currentOrderItems, args['item_name'] ?? '');
        if (target == null) return false;

        final itemId = _asInt(target['item_id']) ?? 0;
        if (itemId <= 0) return false;
        final itemType = (target['item_type'] ?? 'menu_item').toString();
        final itemName = (target['item_name'] ?? 'Item').toString();
        final price = (target['price'] as num?)?.toDouble() ??
            double.tryParse((target['price'] ?? '0').toString()) ??
            0.0;

        dineIn.removeItem(itemId, itemType);
        if (qty > 0) {
          if (itemType == 'custom_deal') {
            final groupSize = _asInt(target['group_size']) ?? 1;
            final rawBundle = target['bundle_items'];
            final bundleItems = (rawBundle is List)
                ? rawBundle
                    .whereType<Map>()
                    .map((entry) => Map<String, dynamic>.from(entry))
                    .toList()
                : <Map<String, dynamic>>[];

            // Keep custom deals as a single logical bundle item.
            dineIn.addCustomDeal(
              customDealId: itemId,
              title: itemName,
              totalPrice: price,
              groupSize: groupSize,
              bundleItems: bundleItems,
            );
          } else {
            dineIn.addItem(itemId, itemType, itemName, price, qty);
          }
        }
        return true;
      }

      final cart = Provider.of<CartProvider>(context, listen: false);
      final cartId = cart.cartId;
      if (cartId == null) return false;
      final requestedName = args['item_name'] ?? '';

      final itemId = await _findItemIdByName(requestedName);
      if (itemId != null) {
        await CartService.setQuantity(
          cartId: cartId,
          itemType: 'menu_item',
          itemId: itemId,
          quantity: qty,
        );
      } else {
        final deal = await _findDealDetailsByName(requestedName);
        final dealId = _asInt(deal?['deal_id']) ?? 0;
        if (dealId <= 0) return false;
        await CartService.setQuantity(
          cartId: cartId,
          itemType: 'deal',
          itemId: dealId,
          quantity: qty,
        );
      }

      if (context.mounted) {
        Provider.of<CartProvider>(context, listen: false).sync();
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  Map<String, dynamic>? _findDineInItemByName(
    List<Map<String, dynamic>> items,
    String name,
  ) {
    final target = name.toLowerCase().trim();
    if (target.isEmpty) return null;

    for (final item in items) {
      final itemName = (item['item_name'] ?? '').toString().toLowerCase().trim();
      if (itemName == target) return item;
    }

    for (final item in items) {
      final itemName = (item['item_name'] ?? '').toString().toLowerCase().trim();
      if (itemName.contains(target) || target.contains(itemName)) {
        return item;
      }
    }
    return null;
  }

  Future<int?> _findItemIdByName(String name) async {
    try {
      final item = await _findItemDetailsByName(name);
      final rawId = item?['item_id'];
      if (rawId is int) return rawId;
      if (rawId is num) return rawId.toInt();
      return int.tryParse((rawId ?? '').toString());
    } catch (_) {
      return null;
    }
  }

  /// Detect cuisine from a raw utterance that may be English, Roman-Urdu, or
  /// written in Urdu script. Returns the canonical chip label used by the
  /// menu / deals screens (e.g. "BBQ", "Desi", "Fast Food", "Chinese",
  /// "Drinks"), or null when nothing matches.
  String? _detectCuisine(String rawQuery) {
    if (rawQuery.trim().isEmpty) return null;
    final q = rawQuery.toLowerCase();

    bool hasAny(Iterable<String> needles) {
      for (final n in needles) {
        if (n.isEmpty) continue;
        if (q.contains(n.toLowerCase())) return true;
      }
      return false;
    }

    // BBQ — tikka / boti / grill / barbeque / Urdu "بار بی کیو" / "تکا" / "بوٹی"
    const bbqKeys = [
      'bbq',
      'b b q',
      'b.b.q',
      'barbe',
      'barbeque',
      'barbecue',
      'tikka',
      'tika',
      'boti',
      'grill',
      'kebab',
      'kabab',
      'seekh',
      // Urdu script
      'بار بی کیو',
      'باربی کیو',
      'بی بی کیو',
      'تکا',
      'تکہ',
      'بوٹی',
      'کباب',
      'سیخ',
    ];
    if (hasAny(bbqKeys)) return 'BBQ';

    // Chinese — chow mein, manchurian, szechuan, Urdu "چائینیز" / "چاؤ مین"
    const chineseKeys = [
      'chinese',
      'chow mein',
      'chowmein',
      'chow-mein',
      'manchur',
      'szechuan',
      'hakka',
      'schezwan',
      // Urdu script
      'چائینیز',
      'چائنیز',
      'چینی کھانا',
      'چاؤ مین',
      'چومین',
    ];
    if (hasAny(chineseKeys)) return 'Chinese';

    // Desi / Pakistani — karahi, biryani, nihari, haleem, handi, pulao
    const desiKeys = [
      'desi',
      'pakistani',
      'indian',
      'karahi',
      'karai',
      'karhai',
      'handi',
      'hondi',
      'biryani',
      'biriyani',
      'biryani',
      'pulao',
      'pulav',
      'nihari',
      'haleem',
      'paya',
      'qorma',
      'korma',
      'daal',
      'dal',
      // Urdu script
      'دیسی',
      'پاکستانی',
      'کڑاہی',
      'کڑاھی',
      'بریانی',
      'پلاؤ',
      'نہاری',
      'حلیم',
      'پائے',
      'قورمہ',
      'ہنڈی',
      'دال',
    ];
    if (hasAny(desiKeys)) return 'Desi';

    // Fast food — burger, fries, pizza, nuggets, zinger, sandwich
    const fastFoodKeys = [
      'fast food',
      'fast-food',
      'fastfood',
      'fast',
      'burger',
      'zinger',
      'fries',
      'nugget',
      'pizza',
      'sandwich',
      'wrap',
      'hotdog',
      'hot dog',
      // Urdu script
      'فاسٹ فوڈ',
      'برگر',
      'زنگر',
      'فرائز',
      'پیزا',
      'سینڈوچ',
    ];
    if (hasAny(fastFoodKeys)) return 'Fast Food';

    // Drinks — cola, juice, tea, chai, water, shake, lassi
    const drinksKeys = [
      'drinks',
      'drink',
      'beverage',
      'cola',
      'coke',
      'pepsi',
      'sprite',
      'juice',
      'shake',
      'smoothie',
      'lassi',
      'chai',
      'tea',
      'water',
      'lemonade',
      // Urdu script
      'ڈرنک',
      'ڈرنکس',
      'مشروب',
      'جوس',
      'شیک',
      'لسی',
      'چائے',
      'پانی',
    ];
    if (hasAny(drinksKeys)) return 'Drinks';

    return null;
  }

  /// Detect menu category (starter / main / side / drink / bread) from a
  /// raw utterance in English, Roman-Urdu, or Urdu script. Returns null
  /// when nothing matches. Category strings match the values used by
  /// [MenuScreen.categories].
  String? _detectCategory(String rawQuery) {
    if (rawQuery.trim().isEmpty) return null;
    final q = rawQuery.toLowerCase();

    bool hasAny(Iterable<String> needles) {
      for (final n in needles) {
        if (n.isEmpty) continue;
        if (q.contains(n.toLowerCase())) return true;
      }
      return false;
    }

    // Drinks first so "chai" / "lassi" route to category too.
    const drinkKeys = [
      'drink',
      'drinks',
      'beverage',
      'beverages',
      'juice',
      'shake',
      'lassi',
      'chai',
      'tea',
      'cola',
      'soda',
      // Urdu
      'ڈرنک',
      'ڈرنکس',
      'مشروب',
      'جوس',
      'لسی',
      'چائے',
      'شیک',
    ];
    if (hasAny(drinkKeys)) return 'drink';

    // Bread
    const breadKeys = [
      'bread',
      'naan',
      'roti',
      'paratha',
      'kulcha',
      'chapati',
      // Urdu
      'روٹی',
      'نان',
      'پراٹھا',
      'کلچہ',
    ];
    if (hasAny(breadKeys)) return 'bread';

    // Starter / appetiser
    const starterKeys = [
      'starter',
      'starters',
      'appetiz',
      'appetis',
      'soup',
      'salad',
      // Urdu
      'اسٹارٹر',
      'سٹارٹر',
      'سوپ',
      'سلاد',
    ];
    if (hasAny(starterKeys)) return 'starter';

    // Side
    const sideKeys = [
      'side',
      'sides',
      'side dish',
      'side-dish',
      'fries',
      'raita',
      // Urdu
      'سائیڈ',
      'رائتہ',
      'فرائز',
    ];
    if (hasAny(sideKeys)) return 'side';

    // Main course
    const mainKeys = [
      'main course',
      'main-course',
      'mains',
      'main',
      'entree',
      'entrée',
      // Urdu
      'مین کورس',
      'مین ڈش',
      'کھانا',
    ];
    if (hasAny(mainKeys)) return 'main';

    return null;
  }
}

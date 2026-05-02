// lib/services/voice_custom_deal_service.dart
//
// Voice custom deal flow:
// 1. POST /deals/custom → CustomDealAgent generates deal
// 2. TTS speaks summary → bottom sheet confirmation dialog
// 3. Kiosk: add as local dine-in custom bundle, Delivery: save to /custom-deal/save
// 4. Delivery only: POST /cart/items/add with item_type=custom_deal
//
// Uses your EXISTING endpoints — no new backend code needed.

import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';

import 'package:khaadim/app_config.dart';
import 'package:khaadim/providers/dine_in_provider.dart';
import 'package:khaadim/services/api_config.dart';
import 'package:khaadim/services/token_storage.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/providers/cart_provider.dart';

/// Signature for an external speaker that can route text through the
/// backend gTTS pipeline (needed for Urdu) and gracefully fall back to the
/// on-device TTS engine. Pass the owning widget's `_speak` to wire it up.
typedef VoiceSpeaker = Future<void> Function(String text, {String? language});

class VoiceCustomDealService {
  final FlutterTts _tts;

  /// Optional hook to let the caller do the actual speaking. When provided,
  /// all `_speak(...)` invocations delegate to it — this is what routes
  /// Urdu messages through the backend gTTS endpoint instead of
  /// `FlutterTts`, which may not have an Urdu voice installed.
  final VoiceSpeaker? _externalSpeaker;

  VoiceCustomDealService(this._tts, {VoiceSpeaker? speaker})
      : _externalSpeaker = speaker;

  // ─────────────────────────────────────────────────────────
  // Main entry — called from VoiceOrderHandler
  // ─────────────────────────────────────────────────────────
  Future<VoiceCustomDealResult> createDeal({
    required String       userQuery,
    required BuildContext context,
    required String       language,
  }) async {
    try {
      final token = await TokenStorage.getToken();
      final isKiosk = AppConfig.isKiosk;

      // ── Step 1: Generate deal via AI ──────────────────────
      final genResp = await http.post(
        Uri.parse('${ApiConfig.baseUrl}/deals/custom'),
        headers: {
          'Content-Type':  'application/json',
          if (token != null && token.isNotEmpty)
            'Authorization': 'Bearer $token',
        },
        body: jsonEncode({'query': userQuery}),
      ).timeout(const Duration(seconds: 25));

      final data = jsonDecode(genResp.body) as Map<String, dynamic>;

      // ── Needs clarification ───────────────────────────────
      if (data['needs_clarification'] == true || data['success'] == false) {
        final displayMsg = (data['message_en'] as String?)
            ?? (data['message']    as String?)
            ?? (language == 'ur'
                ? 'مزید معلومات دیں'
                : 'Please provide more details');

        // Prefer the backend's explicit voice message — it's plain text,
        // shorter, and safe for TTS.
        final voiceMsg = (data['message_voice'] as String?)?.trim();
        await _speak(
          (voiceMsg != null && voiceMsg.isNotEmpty)
              ? voiceMsg
              : displayMsg,
          language: language,
        );

        return VoiceCustomDealResult(
          needsClarification:    true,
          clarificationQuestion: displayMsg,
        );
      }

      // ── Deal generated ────────────────────────────────────
      final items      = (data['items']      as List? ?? [])
          .cast<Map<String, dynamic>>();
      final totalPrice = (data['total_price'] as num?)?.toDouble() ?? 0.0;
      final summaryMsg = language == 'ur'
          ? (data['message']    as String? ?? '')
          : (data['message_en'] as String? ?? '');
      final fullMsg    = data['full_message'] as String? ?? '';

      // Prefer the backend's plain-text `message_voice` — the `message` field
      // is full of markdown (**bold**) and emojis which TTS engines pronounce
      // literally ("sitara sitara" for the `*` char on Urdu voices).
      final voiceFromBackend =
          (data['message_voice'] as String? ?? '').trim();
      final spokenText = voiceFromBackend.isNotEmpty
          ? voiceFromBackend
          : _sanitizeForSpeech(summaryMsg);

      await _speak(spokenText, language: language);

      // ── Step 2: Show confirmation dialog ──────────────────
      if (!context.mounted) {
        return VoiceCustomDealResult(confirmed: false);
      }
      final confirmed = await _showConfirmDialog(
        context:    context,
        items:      items,
        totalPrice: totalPrice,
        fullMsg:    fullMsg,
        language:   language,
      );

      if (!confirmed) {
        await _speak(language == 'ur' ? 'ٹھیک ہے، ڈیل کینسل' : 'Deal cancelled.', language: language);
        return VoiceCustomDealResult(confirmed: false);
      }

      // ── Kiosk path: store as local custom bundle in dine-in provider ──
      if (isKiosk) {
        if (!context.mounted) {
          return const VoiceCustomDealResult(confirmed: true);
        }

        final dineIn = Provider.of<DineInProvider>(context, listen: false);
        final customDealId = -DateTime.now().millisecondsSinceEpoch;

        final computedGroupSize = items.fold<int>(
          0,
          (sum, item) {
            final rawQty = item['quantity'];
            final qty = rawQty is int
                ? rawQty
                : int.tryParse((rawQty ?? '1').toString()) ?? 1;
            return sum + (qty > 0 ? qty : 1);
          },
        );

        dineIn.addCustomDeal(
          customDealId: customDealId,
          title: language == 'ur' ? 'کسٹم ڈیل' : 'Custom Deal',
          totalPrice: totalPrice,
          groupSize: computedGroupSize > 0 ? computedGroupSize : items.length,
          bundleItems: items,
        );

        final doneMsg = language == 'ur'
            ? 'کسٹم ڈیل آپ کے آرڈر میں شامل کر دی گئی ہے۔'
            : 'Custom deal has been added to your order.';
        await _speak(doneMsg, language: language);

        return const VoiceCustomDealResult(confirmed: true, addedToCart: true);
      }

      // ── Step 3: Save deal via /custom-deal/save ───────────
      final saveResp = await http.post(
        Uri.parse('${ApiConfig.baseUrl}/custom-deal/save'),
        headers: {
          'Content-Type':  'application/json',
          if (token != null && token.isNotEmpty)
            'Authorization': 'Bearer $token',
        },
        body: jsonEncode({
          'group_size':       items.length,
          'total_price':      totalPrice,
          'discount_amount':  0.0,
          'items': items.map((i) => {
            'item_id':    i['item_id'],
            'item_name':  i['item_name'],
            'quantity':   i.containsKey('quantity') ? i['quantity'] : 1,
            'unit_price': (i['price'] as num?)?.toDouble()
                ?? (i['item_price'] as num?)?.toDouble()
                ?? 0.0,
          }).toList(),
        }),
      ).timeout(const Duration(seconds: 15));

      final saveData = jsonDecode(saveResp.body) as Map<String, dynamic>;
      if (saveData['success'] != true) {
        return VoiceCustomDealResult(
          confirmed: true,
          error: language == 'ur' ? 'ڈیل محفوظ نہیں ہو سکی' : 'Could not save deal',
        );
      }

      final customDealId = saveData['custom_deal_id'] as int;

      // ── Step 4: Add to cart via /cart/items/add ───────────
      if (!context.mounted) {
        return VoiceCustomDealResult(confirmed: true);
      }
      final cart   = Provider.of<CartProvider>(context, listen: false);
      final cartId = cart.cartId;
      if (cartId == null) {
        return VoiceCustomDealResult(
          confirmed: true,
          error: language == 'ur' ? 'کارٹ نہیں ملی' : 'Cart not found',
        );
      }

      await CartService.addItem(
        cartId:   cartId,
        itemType: 'custom_deal',
        itemId:   customDealId,
        quantity: 1,
      );

      if (context.mounted) {
        Provider.of<CartProvider>(context, listen: false).sync();
      }

      final doneMsg = language == 'ur'
          ? 'ڈیل کارٹ میں شامل کر دی گئی!'
          : 'Deal added to your cart!';
      await _speak(doneMsg, language: language);

      return VoiceCustomDealResult(confirmed: true, addedToCart: true);

    } catch (e, st) {
      // Surface the real exception in logs so subsequent regressions are
      // diagnosable. The user-facing message stays polite and localised.
      debugPrint('[VoiceCustomDeal] Error: $e');
      debugPrint('[VoiceCustomDeal] Stack: $st');
      return VoiceCustomDealResult(
        error: language == 'ur' ? 'ڈیل بنانے میں خرابی' : 'Error creating deal',
      );
    }
  }

  // ─────────────────────────────────────────────────────────
  // Confirmation bottom sheet
  // ─────────────────────────────────────────────────────────
  Future<bool> _showConfirmDialog({
    required BuildContext              context,
    required List<Map<String, dynamic>> items,
    required double                    totalPrice,
    required String                    fullMsg,
    required String                    language,
  }) async {
    final ur = language == 'ur';

    final result = await showModalBottomSheet<bool>(
      context:            context,
      isScrollControlled: true,
      backgroundColor:    Colors.transparent,
      builder:            (_) => _DealConfirmSheet(
        items:      items,
        totalPrice: totalPrice,
        isUrdu:     ur,
      ),
    );
    return result ?? false;
  }

  Future<void> _speak(String text, {String? language}) async {
    try {
      final clean = _sanitizeForSpeech(text);
      if (clean.isEmpty) return;

      // Prefer the owner's speak pipeline — it already routes Urdu through
      // the backend gTTS endpoint and only falls back to `FlutterTts` when
      // that fails. Using `_tts.speak` directly here would mean no Urdu
      // audio at all on devices without a native Urdu voice.
      final speaker = _externalSpeaker;
      if (speaker != null) {
        await speaker(clean, language: language);
        return;
      }

      await _tts.stop();
      if (language != null) {
        await _tts.setLanguage(language == 'ur' ? 'ur-PK' : 'en-US');
      }
      await _tts.speak(clean);
    } catch (e, st) {
      debugPrint('[VoiceCustomDeal] TTS speak failed: $e\n$st');
    }
  }

  /// Removes markdown decorations (`**`, `#`, backticks, bullets) and all
  /// emoji / pictographic symbols without using supplementary-plane regex
  /// escapes — which can throw on older Dart SDKs when the regex is first
  /// compiled. Iterating code units is portable and fast.
  String _sanitizeForSpeech(String input) {
    if (input.isEmpty) return input;

    var s = input;

    // Strip fenced / inline code blocks.
    s = s.replaceAll(RegExp(r'```[\s\S]*?```'), ' ');
    s = s.replaceAll(RegExp(r'`([^`]*)`'), r' $1 ');

    // Markdown link [text](url) → text
    s = s.replaceAllMapped(
      RegExp(r'\[([^\]]+)\]\([^)]*\)'),
      (m) => m.group(1) ?? '',
    );

    // Strip leading heading / bullet markers line-by-line. Dart's RegExp
    // does NOT accept the inline `(?m)` flag (it's ECMA-flavoured) — we
    // must pass `multiLine: true` explicitly, or the RegExp constructor
    // throws FormatException and the whole voice reply fails silently.
    s = s.replaceAll(RegExp(r'^\s*#{1,6}\s+', multiLine: true), '');
    s = s.replaceAll(RegExp(r'^\s*[-*•]\s+', multiLine: true), '');

    // Remove remaining markdown emphasis characters.
    s = s.replaceAll(RegExp(r'[*_~`#>]+'), ' ');

    // Replace the multiplication sign ('×') that appears in deal lists.
    s = s.replaceAll('×', ' x ');

    // Drop emojis / pictographs using a manual codepoint filter. This avoids
    // the `unicode: true` + `\u{1F300}` regex syntax which fails on some
    // Dart/Flutter runtimes.
    final buf = StringBuffer();
    final runes = s.runes.toList();
    for (final rune in runes) {
      if (_isPictographOrSymbol(rune)) {
        buf.write(' ');
      } else {
        buf.writeCharCode(rune);
      }
    }
    s = buf.toString();

    // Collapse whitespace.
    s = s.replaceAll(RegExp(r'\s+'), ' ').trim();
    return s;
  }

  bool _isPictographOrSymbol(int rune) {
    // Misc symbols & dingbats (BMP).
    if (rune >= 0x2600 && rune <= 0x27BF) return true;
    // Supplemental symbols & pictographs, emoticons, transport, etc.
    if (rune >= 0x1F000 && rune <= 0x1FAFF) return true;
    // Variation selectors and zero-width joiner used in emoji sequences.
    if (rune == 0x200D || rune == 0xFE0F) return true;
    return false;
  }
}

// ─────────────────────────────────────────────────────────────
// Confirmation bottom sheet widget
// ─────────────────────────────────────────────────────────────
class _DealConfirmSheet extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  final double                     totalPrice;
  final bool                       isUrdu;

  const _DealConfirmSheet({
    required this.items,
    required this.totalPrice,
    required this.isUrdu,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      decoration: BoxDecoration(
        color:        theme.colorScheme.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: EdgeInsets.fromLTRB(
          20, 16, 20,
          20 + MediaQuery.of(context).viewInsets.bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [

          // Handle bar
          Center(child: Container(
            width: 40, height: 4,
            decoration: BoxDecoration(
              color: Colors.grey[300],
              borderRadius: BorderRadius.circular(10),
            ),
          )),
          const SizedBox(height: 16),

          // Title
          Row(children: [
            const Icon(Icons.auto_awesome, color: Colors.orange, size: 22),
            const SizedBox(width: 8),
            Text(
              isUrdu ? 'آپ کی کسٹم ڈیل' : 'Your Custom Deal',
              style: theme.textTheme.titleLarge
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
          ]),
          const SizedBox(height: 16),

          // Items
          ...items.map((item) {
            final name = item['item_name']?.toString() ?? '';
            final qty  = item['quantity'] ?? 1;
            final price = ((item['price'] as num?)
                ?? (item['item_price'] as num?)
                ?? 0).toDouble();
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('$qty× $name',
                      style: theme.textTheme.bodyMedium),
                  Text('Rs ${price.toStringAsFixed(0)}',
                      style: TextStyle(color: Colors.grey[600], fontSize: 13)),
                ],
              ),
            );
          }),

          const Divider(height: 24),

          // Total
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(isUrdu ? 'کل قیمت' : 'Total',
                  style: const TextStyle(
                      fontWeight: FontWeight.bold, fontSize: 16)),
              Text('Rs ${totalPrice.toStringAsFixed(0)}',
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize:   16,
                    color:      theme.colorScheme.primary,
                  )),
            ],
          ),
          const SizedBox(height: 20),

          // Buttons
          Row(children: [
            Expanded(
              child: OutlinedButton(
                onPressed: () => Navigator.pop(context, false),
                child: Text(isUrdu ? 'کینسل' : 'Cancel'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.orange),
                onPressed: () => Navigator.pop(context, true),
                child: Text(
                  isUrdu ? 'کارٹ میں شامل کریں' : 'Add to Cart',
                  style: const TextStyle(color: Colors.white),
                ),
              ),
            ),
          ]),

          const SizedBox(height: 8),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// Result model
// ─────────────────────────────────────────────────────────────
class VoiceCustomDealResult {
  final bool   needsClarification;
  final String clarificationQuestion;
  final bool   confirmed;
  final bool   addedToCart;
  final String error;

  const VoiceCustomDealResult({
    this.needsClarification    = false,
    this.clarificationQuestion = '',
    this.confirmed             = false,
    this.addedToCart           = false,
    this.error                 = '',
  });
}
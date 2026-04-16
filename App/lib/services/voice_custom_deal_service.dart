// lib/services/voice_custom_deal_service.dart
//
// Voice custom deal flow:
// 1. POST /voice/custom_deal → CustomDealAgent generates deal
// 2. TTS speaks summary → bottom sheet confirmation dialog
// 3. User confirms → POST /custom-deal/save → get custom_deal_id
// 4. POST /cart/items/add with item_type=custom_deal
//
// Uses your EXISTING endpoints — no new backend code needed.

import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';

import 'package:khaadim/services/api_config.dart';
import 'package:khaadim/services/token_storage.dart';
import 'package:khaadim/services/cart_service.dart';
import 'package:khaadim/providers/cart_provider.dart';

class VoiceCustomDealService {
  final FlutterTts _tts;

  VoiceCustomDealService(this._tts);

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

      // ── Step 1: Generate deal via AI ──────────────────────
      final genResp = await http.post(
        Uri.parse('${ApiConfig.baseUrl}/voice/custom_deal'),
        headers: {
          'Content-Type':  'application/json',
          if (token != null) 'Authorization': 'Bearer $token',
        },
        body: jsonEncode({'user_query': userQuery}),
      ).timeout(const Duration(seconds: 25));

      final data = jsonDecode(genResp.body) as Map<String, dynamic>;

      // ── Needs clarification ───────────────────────────────
      if (data['needs_clarification'] == true || data['success'] == false) {
        final msg = language == 'ur'
            ? (data['message']    as String? ?? 'مزید معلومات دیں')
            : (data['message_en'] as String? ?? 'Please provide more details');
        await _speak(msg);
        return VoiceCustomDealResult(
          needsClarification:    true,
          clarificationQuestion: msg,
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

      // Speak the summary
      await _speak(summaryMsg);

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
        await _speak(language == 'ur' ? 'ٹھیک ہے، ڈیل کینسل' : 'Deal cancelled.');
        return VoiceCustomDealResult(confirmed: false);
      }

      // ── Step 3: Save deal via /custom-deal/save ───────────
      final saveResp = await http.post(
        Uri.parse('${ApiConfig.baseUrl}/custom-deal/save'),
        headers: {
          'Content-Type':  'application/json',
          if (token != null) 'Authorization': 'Bearer $token',
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
      await _speak(doneMsg);

      return VoiceCustomDealResult(confirmed: true, addedToCart: true);

    } catch (e) {
      debugPrint('[VoiceCustomDeal] Error: $e');
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

  Future<void> _speak(String text) async {
    if (text.isEmpty) return;
    await _tts.stop();
    await _tts.speak(text);
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
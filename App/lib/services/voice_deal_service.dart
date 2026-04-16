// lib/services/voice_deal_service.dart
// REPLACE existing file entirely.
//
// Key changes:
//   1. Uses nav.openDealsWithFilter() instead of switchTab(2)
//      → passes cuisineFilter + servingFilter so OffersScreen pre-filters
//      → passes highlightDealId so matched deal gets orange border + scroll
//   2. Accepts ConversationMemory — records assistant turns
//   3. No-match bottom sheet shows closest available sizes
//   4. "Yes" → returns customDealQuery so VoiceOrderHandler runs custom deal flow

import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:http/http.dart' as http;

import 'package:khaadim/services/api_config.dart';
import 'package:khaadim/services/conversation_memory.dart';
import 'package:khaadim/services/token_storage.dart';
import 'package:khaadim/widgets/voice_nav_callbacks.dart';

class VoiceDealResult {
  final bool found;
  final bool navigated;
  final bool suggestCustom;
  final String message;
  final String customDealQuery;

  const VoiceDealResult({
    this.found = false,
    this.navigated = false,
    this.suggestCustom = false,
    this.message = '',
    this.customDealQuery = '',
  });
}

class VoiceDealService {
  final FlutterTts _tts;
  VoiceDealService(this._tts);

  Future<VoiceDealResult> handleDealSearch({
    required String cuisine,
    required int personCount,
    required BuildContext context,
    required String language,
    required VoiceNavCallbacks? nav,
    ConversationMemory? memory,
  }) async {
    try {
      final token = await TokenStorage.getToken();
      final params = <String, String>{};
      if (cuisine.isNotEmpty) params['cuisine'] = cuisine;
      if (personCount > 0) params['person_count'] = personCount.toString();

      final uri = Uri.parse('${ApiConfig.baseUrl}/voice/deal_check')
          .replace(queryParameters: params);
      final resp = await http.get(uri, headers: {
        if (token != null) 'Authorization': 'Bearer $token',
      }).timeout(const Duration(seconds: 8));

      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      final ur = language == 'ur';
      final msg = ur
          ? (data['message'] as String? ?? '')
          : (data['message_en'] as String? ?? '');

      // ── Deal(s) found ──────────────────────────────────────
      if (data['exists'] == true) {
        await _speak(msg);
        memory?.add(role: 'assistant', text: msg);

        // Pick the best matching deal_id to highlight (first result)
        final deals =
            (data['deals'] as List? ?? []).cast<Map<String, dynamic>>();
        final highlightId =
            deals.isNotEmpty ? deals.first['deal_id'] as int? : null;

        // Navigate to Deals tab with pre-applied cuisine + serving filters
        final servingStr = personCount > 0 ? personCount.toString() : null;
        nav?.openDealsWithFilter(
          cuisineFilter: cuisine.isNotEmpty ? cuisine : null,
          servingFilter: servingStr,
          highlightDealId: highlightId,
        );

        return VoiceDealResult(found: true, navigated: true, message: msg);
      }

      // ── No exact deal — suggest closest + custom ───────────
      await _speak(msg);
      memory?.add(role: 'assistant', text: msg);

      if (data['suggest_custom'] == true && context.mounted) {
        final availableSizes = (data['available_sizes'] as List? ?? [])
            .map((s) => s is int ? s : int.tryParse(s.toString()) ?? 0)
            .where((s) => s > 0)
            .toList();

        final confirmed = await _showNoDealsSheet(
          context: context,
          cuisine: cuisine,
          personCount: personCount,
          availableSizes: availableSizes,
          isUrdu: ur,
        );

        if (confirmed) {
          final query = (data['custom_query'] as String?) ??
              'create ${cuisine.toLowerCase()} deal for $personCount people';

          // Save conversation turns so next voice prompt has context
          final yesText = ur ? 'ہاں، کسٹم ڈیل بناؤ' : 'Yes, create custom deal';
          memory?.add(role: 'user', text: yesText);
          memory?.add(
              role: 'assistant',
              text: ur
                  ? 'ٹھیک ہے! آپ کی کسٹم ڈیل بنا رہا ہوں...'
                  : 'Creating your custom deal...');

          return VoiceDealResult(
            found: false,
            suggestCustom: true,
            customDealQuery: query,
            message: msg,
          );
        }

        // User said No — show closest deals on Deals tab anyway
        nav?.openDealsWithFilter(
          cuisineFilter: cuisine.isNotEmpty ? cuisine : null,
          servingFilter: null, // show all sizes since exact didn't match
        );
        return VoiceDealResult(
          found: false,
          navigated: true,
          // ↓ always set this so VoiceCommandService can store it
          customDealQuery:
              'create ${cuisine.toLowerCase()} deal for $personCount people',
          message: msg,
        );
      }

      return VoiceDealResult(found: false, message: msg);
    } catch (e) {
      debugPrint('[VoiceDealService] Error: $e');
      final fallback =
          language == 'ur' ? 'ڈیل معلومات نہیں مل سکی' : 'Could not load deals';
      return VoiceDealResult(found: false, message: fallback);
    }
  }

  // ─────────────────────────────────────────────────────────
  // Bottom sheet — "No X-person deal. Want a custom one?"
  // Shows available sizes so user knows what exists.
  // ─────────────────────────────────────────────────────────
  Future<bool> _showNoDealsSheet({
    required BuildContext context,
    required String cuisine,
    required int personCount,
    required List<int> availableSizes,
    required bool isUrdu,
  }) async {
    final result = await showModalBottomSheet<bool>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) {
        final theme = Theme.of(ctx);
        return Container(
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
          ),
          padding: EdgeInsets.fromLTRB(
              20, 16, 20, 24 + MediaQuery.of(ctx).viewInsets.bottom),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            // Handle bar
            Center(
                child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                  color: Colors.grey[300],
                  borderRadius: BorderRadius.circular(10)),
            )),
            const SizedBox(height: 20),

            const Icon(Icons.search_off_rounded,
                size: 44, color: Colors.orange),
            const SizedBox(height: 12),

            // Title
            Text(
              isUrdu
                  ? '${cuisine.isNotEmpty ? cuisine : "اس"} میں $personCount افراد کے لیے ڈیل نہیں ملی'
                  : 'No ${cuisine.isNotEmpty ? cuisine : ""} deal for $personCount people',
              style: theme.textTheme.titleMedium
                  ?.copyWith(fontWeight: FontWeight.bold),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),

            // Show available sizes
            if (availableSizes.isNotEmpty)
              Text(
                isUrdu
                    ? 'دستیاب سائز: ${availableSizes.map((s) => '$s افراد').join('، ')}'
                    : 'Available: ${availableSizes.map((s) => '$s person').join(', ')}',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: Colors.grey[600]),
                textAlign: TextAlign.center,
              ),
            const SizedBox(height: 8),

            Text(
              isUrdu
                  ? 'کیا میں آپ کے لیے بجٹ فرینڈلی کسٹم ڈیل بناؤں؟'
                  : 'Shall I create a budget-friendly custom deal for you?',
              style:
                  theme.textTheme.bodyMedium?.copyWith(color: Colors.grey[600]),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),

            Row(children: [
              Expanded(
                  child: OutlinedButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: Text(isUrdu ? 'نہیں شکریہ' : 'No thanks'),
              )),
              const SizedBox(width: 12),
              Expanded(
                  child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.orange,
                    padding: const EdgeInsets.symmetric(vertical: 14)),
                onPressed: () => Navigator.pop(ctx, true),
                child: Text(
                  isUrdu ? '✨ ہاں، بناؤ!' : '✨ Yes, create!',
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.bold),
                ),
              )),
            ]),
          ]),
        );
      },
    );
    return result ?? false;
  }

  Future<void> _speak(String text) async {
    if (text.isEmpty) return;
    await _tts.stop();
    await _tts.speak(text);
  }
}

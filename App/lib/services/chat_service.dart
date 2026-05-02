import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'api_config.dart';
import 'api_client.dart';
import 'token_storage.dart';

class ChatServiceException implements Exception {
  final String message;
  const ChatServiceException(this.message);

  @override
  String toString() => message;
}

class ChatService {
  static String get _base => ApiConfig.baseUrl;

  static const Duration timeout = Duration(seconds: 120);

  static String extractTranscript(Map<String, dynamic> payload) {
    final candidates = <String?>[
      payload['transcript']?.toString(),
      payload['text']?.toString(),
      payload['recognized_text']?.toString(),
      payload['user_text']?.toString(),
    ];

    for (final c in candidates) {
      final v = (c ?? '').trim();
      if (v.isNotEmpty) return v;
    }
    return '';
  }

  Future<Map<String, dynamic>> sendTextMessage(
      String sessionId,
      String text,
      String lang,
      ) async {
    final token = await TokenStorage.getToken();
    final uri = Uri.parse("$_base/chat");

    final res = await http
        .post(
      uri,
      headers: {
        "Content-Type": "application/json",
        if (token != null && token.isNotEmpty)
          "Authorization": "Bearer $token",
      },
      body: jsonEncode({
        "session_id": sessionId,
        "message": text,
        "language": lang,
      }),
    )
        .timeout(timeout);

    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw ChatServiceException(
        "Chat text failed: ${res.statusCode} ${res.body}",
      );
    }

    final decoded = jsonDecode(res.body);
    return (decoded is Map<String, dynamic>) ? decoded : {"reply": ""};
  }

  /// [conversationHistory] — pass memory.toApiHistory() from ConversationMemory.
  /// Backend receives it as a JSON string in the multipart form field.
  Future<Map<String, dynamic>> sendVoiceMessage(
      String sessionId,
      File audioFile,
      String mode,
      String lang, {
        List<Map<String, String>> conversationHistory = const [],
      }) async {
    final token = await TokenStorage.getToken();
    final uri = Uri.parse("$_base/voice_chat");

    final req = http.MultipartRequest("POST", uri);

    if (token != null && token.isNotEmpty) {
      req.headers["Authorization"] = "Bearer $token";
    }

    req.fields["session_id"] = sessionId;
    req.fields["language"] = lang;

    // Send conversation history as JSON string so backend can parse it
    req.fields["conversation_history"] = jsonEncode(conversationHistory);

    req.files.add(await http.MultipartFile.fromPath("file", audioFile.path));

    final streamed = await req.send().timeout(timeout);
    final body = await streamed.stream.bytesToString();

    if (streamed.statusCode < 200 || streamed.statusCode >= 300) {
      throw ChatServiceException(
        "Chat voice failed: ${streamed.statusCode} $body",
      );
    }

    final decoded = jsonDecode(body);
    return (decoded is Map<String, dynamic>)
        ? decoded
        : {"transcript": "", "reply": ""};
  }

  Future<String> getOrderStatus() async {
    try {
      final res = await ApiClient.getJson(
        '/orders/my',
        auth: true,
        timeout: ApiClient.defaultTimeout,
      );

      final orders = (res['orders'] as List? ?? []).cast<dynamic>();
      if (orders.isEmpty) {
        return 'No recent orders found.';
      }

      final latest = orders.first as Map<String, dynamic>;
      final orderId = latest['order_id']?.toString() ?? 'N/A';
      final status = latest['order_status']?.toString() ??
          latest['status']?.toString() ??
          'processing';

      return 'Your latest order #$orderId is currently $status.';
    } catch (_) {
      return 'Could not fetch order status right now.';
    }
  }

  Future<String> getVoiceRecommendations({String language = 'en'}) async {
    try {
      final res = await ApiClient.getJson(
        '/personalization/recommendations',
        auth: true,
        timeout: ApiClient.defaultTimeout,
      );

      final items = (res['recommended_items'] as List? ?? []).cast<dynamic>();
      final deals = (res['recommended_deals'] as List? ?? []).cast<dynamic>();

      if (items.isEmpty && deals.isEmpty) {
        return language == 'ur'
            ? 'ابھی کوئی خاص سفارش دستیاب نہیں۔'
            : 'No recommendations available right now.';
      }

      final parts = <String>[];

      // Top 2 menu items with reasons
      for (final e in items.take(2)) {
        final map = e as Map<String, dynamic>;
        final name = map['item_name']?.toString() ?? '';
        final reason = map['reason']?.toString() ?? '';
        final reasonUr = map['reason_ur']?.toString() ?? reason;
        if (name.isEmpty) continue;
        parts.add(language == 'ur' ? '$name (کیونکہ $reasonUr)' : '$name ($reason)');
      }

      // Top 1 deal with reason
      if (deals.isNotEmpty) {
        final d = deals.first as Map<String, dynamic>;
        final name = d['deal_name']?.toString() ?? '';
        final reason = d['reason']?.toString() ?? '';
        final reasonUr = d['reason_ur']?.toString() ?? reason;
        if (name.isNotEmpty) {
          parts.add(language == 'ur'
              ? 'اور ڈیل: $name (کیونکہ $reasonUr)'
              : 'and deal: $name ($reason)');
        }
      }

      if (parts.isEmpty) {
        return language == 'ur'
            ? 'سفارشات دستیاب ہیں، براہِ کرم ہوم اسکرین دیکھیں۔'
            : 'Recommendations are ready on your home screen.';
      }

      return language == 'ur'
          ? 'آپ کے لیے سفارشات: ${parts.join('، ')}'
          : 'Recommended for you: ${parts.join(', ')}';
    } catch (_) {
      return language == 'ur'
          ? 'سفارشات حاصل نہیں ہو سکیں۔'
          : 'Could not fetch recommendations right now.';
    }
  }

  Future<Map<String, dynamic>?> getUpsellSuggestion({
    required String lastItemName,
    required List<String> cartItems,
  }) async {
    try {
      final res = await ApiClient.postJson(
        '/chat',
        auth: true,
        timeout: ApiClient.defaultTimeout,
        body: {
          'session_id': 'upsell-session',
          'message':
          'Suggest one upsell item for cart: ${cartItems.join(', ')}. Last item: $lastItemName',
          'language': 'en',
        },
      );

      final reply = (res['reply'] ?? '').toString().trim();
      if (reply.isEmpty) return null;
      return {
        'success': true,
        'suggestion_en': reply,
        'suggestion_ur': reply,
      };
    } catch (_) {
      return null;
    }
  }
}

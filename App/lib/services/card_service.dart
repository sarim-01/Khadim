import 'api_client.dart';

class CardService {
  static Future<List<Map<String, dynamic>>> getSavedCards() async {
    final res = await ApiClient.getJson('/cards', auth: true);
    final raw = res['cards'] as List<dynamic>? ?? [];
    return raw.cast<Map<String, dynamic>>();
  }

  static Future<Map<String, dynamic>> addCard({
    required String cardType,
    required String last4,
    required String cardholderName,
    required String expiry,
  }) async {
    return ApiClient.postJson(
      '/cards/add',
      auth: true,
      body: {
        'card_type': cardType,
        'last4': last4,
        'cardholder_name': cardholderName,
        'expiry': expiry,
      },
    );
  }

  static Future<void> deleteCard({required int cardId}) async {
    await ApiClient.deleteJson('/cards/$cardId', auth: true);
  }
}

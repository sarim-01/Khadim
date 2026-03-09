import 'api_client.dart';

class PaymentService {
  // Legacy singleton kept so existing references don't break
  static final PaymentService _instance = PaymentService._internal();
  factory PaymentService() => _instance;
  PaymentService._internal();

  static Future<Map<String, dynamic>> processPayment({
    required String cartId,
    required double amount,
    required int cardId,
  }) async {
    return ApiClient.postJson(
      '/payment/process',
      auth: true,
      body: {
        'cart_id': cartId,
        'amount': amount,
        'card_id': cardId,
      },
    );
  }
}


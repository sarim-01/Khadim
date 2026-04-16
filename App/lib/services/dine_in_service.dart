import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_config.dart';

class DineInService {
  static String get _baseUrl => ApiConfig.baseUrl;

  Future<Map<String, dynamic>> tableLogin(
    String tableNumber,
    String pin,
  ) async {
    final url = Uri.parse('$_baseUrl/dine-in/table-login');

    final response = await http.post(
      url,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'table_number': tableNumber, 'pin': pin}),
    );

    return _handleResponse(response);
  }

  Future<Map<String, dynamic>> placeOrder(
    String sessionId,
    List<Map<String, dynamic>> items,
  ) async {
    final url = Uri.parse('$_baseUrl/dine-in/order');

    final response = await http.post(
      url,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'session_id': sessionId, 'items': items}),
    );

    return _handleResponse(response);
  }

  Future<List<Map<String, dynamic>>> fetchRecommendations(
    String sessionId,
    List<Map<String, dynamic>> items,
  ) async {
    final url = Uri.parse('$_baseUrl/dine-in/recommendations');

    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'session_id': sessionId, 'items': items}),
      );

      final data = _handleResponse(response);
      final raw = data['recommendations'] as List<dynamic>? ?? [];
      return raw
          .whereType<Map>()
          .map((entry) => Map<String, dynamic>.from(entry))
          .toList();
    } catch (_) {
      return [];
    }
  }

  Future<List<Map<String, dynamic>>> fetchSessionOrders(
    String sessionId, {
    String? token,
  }) async {
    final url = Uri.parse('$_baseUrl/dine-in/sessions/$sessionId/orders');

    final response = await http.get(
      url,
      headers: {
        'Content-Type': 'application/json',
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
      },
    );

    final decoded = _handleResponse(response);
    final raw =
        decoded['orders'] ?? decoded['rounds'] ?? decoded['data'] ?? decoded;
    if (raw is! List) {
      return <Map<String, dynamic>>[];
    }

    return raw
        .whereType<Map>()
        .map((entry) => Map<String, dynamic>.from(entry))
        .toList();
  }

  Future<Map<String, dynamic>> callWaiter(
    String sessionId, {
    String? token,
    bool forCashPayment = false,
  }) async {
    final uri =
        Uri.parse('$_baseUrl/dine-in/sessions/$sessionId/call-waiter').replace(
      queryParameters:
          forCashPayment ? <String, String>{'for_cash_payment': 'true'} : null,
    );

    final response = await http.post(
      uri,
      headers: {
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
      },
    );

    return _handleResponse(response);
  }

  Future<Map<String, dynamic>> fetchWaiterCallStatus(
    String sessionId,
    String callId, {
    String? token,
  }) async {
    final url = Uri.parse(
      '$_baseUrl/dine-in/sessions/$sessionId/waiter-calls/$callId/status',
    );

    final response = await http.get(
      url,
      headers: {
        'Content-Type': 'application/json',
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
      },
    );

    return _handleResponse(response);
  }

  Future<Map<String, dynamic>> settleSessionPayment(
    String sessionId,
    String paymentMethod, {
    String? token,
  }) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/dine-in/sessions/$sessionId/settle-payment'),
      headers: {
        'Content-Type': 'application/json',
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
      },
      body: jsonEncode({'payment_method': paymentMethod}),
    );

    return _handleResponse(response);
  }

  Future<Map<String, dynamic>> endSession(
    String sessionId, {
    String? token,
  }) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/dine-in/sessions/$sessionId/end'),
      headers: {
        'Content-Type': 'application/json',
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
      },
    );

    return _handleResponse(response);
  }

  Future<Map<String, dynamic>> fetchSessionOrderTracking(
    String sessionId,
    int orderId, {
    String? token,
  }) async {
    final url = Uri.parse(
      '$_baseUrl/dine-in/sessions/$sessionId/orders/$orderId/tracking',
    );

    final response = await http.get(
      url,
      headers: {
        'Content-Type': 'application/json',
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
      },
    );

    return _handleResponse(response);
  }

  Map<String, dynamic> _handleResponse(http.Response response) {
    dynamic decoded = <String, dynamic>{};
    if (response.body.isNotEmpty) {
      try {
        decoded = jsonDecode(response.body);
      } catch (_) {
        decoded = response.body;
      }
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    }

    String errorMessage = 'Request failed';
    if (decoded is Map<String, dynamic> && decoded['detail'] != null) {
      errorMessage = decoded['detail'].toString();
    } else if (decoded is String && decoded.trim().isNotEmpty) {
      errorMessage = decoded;
    } else if (response.body.isNotEmpty) {
      errorMessage = response.body;
    }

    throw Exception(errorMessage);
  }
}

import 'dart:convert';

import 'package:http/http.dart' as http;

class DineInService {
  static const String _baseUrl = 'http://192.168.100.30:8000';

  Future<Map<String, dynamic>> tableLogin(String tableNumber, String pin) async {
    final url = Uri.parse('$_baseUrl/dine-in/table-login');

    final response = await http.post(
      url,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'table_number': tableNumber,
        'pin': pin,
      }),
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
      body: jsonEncode({
        'session_id': sessionId,
        'items': items,
      }),
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
        body: jsonEncode({
          'session_id': sessionId,
          'items': items,
        }),
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

  Map<String, dynamic> _handleResponse(http.Response response) {
    final dynamic decoded =
        response.body.isNotEmpty ? jsonDecode(response.body) : {};

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    }

    String errorMessage = 'Request failed';
    if (decoded is Map<String, dynamic> && decoded['detail'] != null) {
      errorMessage = decoded['detail'].toString();
    } else if (response.body.isNotEmpty) {
      errorMessage = response.body;
    }

    throw Exception(errorMessage);
  }
}
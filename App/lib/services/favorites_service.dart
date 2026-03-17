import 'dart:convert';
import 'package:http/http.dart' as http;

import 'api_config.dart';
import 'auth_headers.dart';

class FavoritesService {
  static Future<List<Map<String, dynamic>>> getFavorites() async {
    final Map<String, String> headers = await AuthHeaders.getHeaders();

    final Uri url = Uri.parse('${ApiConfig.baseUrl}/favorites');

    final http.Response response = await http.get(
      url,
      headers: headers,
    );

    final dynamic decodedBody =
    response.body.isNotEmpty ? jsonDecode(response.body) : [];

    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (decodedBody is List) {
        return decodedBody
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
      }

      if (decodedBody is Map<String, dynamic> &&
          decodedBody['favorites'] is List) {
        return (decodedBody['favorites'] as List)
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
      }

      return [];
    }

    String errorMessage = 'Failed to load favorites';
    if (decodedBody is Map<String, dynamic> && decodedBody['detail'] != null) {
      errorMessage = decodedBody['detail'].toString();
    }

    throw Exception(errorMessage);
  }

  static Future<void> addFavorite({
    required int entityId,
    String entityType = 'ITEM',
  }) async {
    final Map<String, String> headers = await AuthHeaders.getHeaders();

    final Uri url = Uri.parse('${ApiConfig.baseUrl}/favorites');

    final http.Response response = await http.post(
      url,
      headers: headers,
      body: jsonEncode({
        'entity_id': entityId,
        'entity_type': entityType,
      }),
    );

    final dynamic decodedBody =
    response.body.isNotEmpty ? jsonDecode(response.body) : {};

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return;
    }

    String errorMessage = 'Failed to add favorite';
    if (decodedBody is Map<String, dynamic> && decodedBody['detail'] != null) {
      errorMessage = decodedBody['detail'].toString();
    }

    throw Exception(errorMessage);
  }

  static Future<void> removeFavorite({
    required int entityId,
    String entityType = 'ITEM',
  }) async {
    final Map<String, String> headers = await AuthHeaders.getHeaders();

    final Uri url = Uri.parse(
      '${ApiConfig.baseUrl}/favorites?entity_id=$entityId&entity_type=$entityType',
    );

    final http.Response response = await http.delete(
      url,
      headers: headers,
    );

    final dynamic decodedBody =
    response.body.isNotEmpty ? jsonDecode(response.body) : {};

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return;
    }

    String errorMessage = 'Failed to remove favorite';
    if (decodedBody is Map<String, dynamic> && decodedBody['detail'] != null) {
      errorMessage = decodedBody['detail'].toString();
    }

    throw Exception(errorMessage);
  }
}
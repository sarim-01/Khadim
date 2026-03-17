import 'dart:convert';
import 'package:http/http.dart' as http;

import 'api_config.dart';
import 'auth_headers.dart';

class FeedbackService {
  static Future<Map<String, dynamic>> submitFeedback({
    required int rating,
    required String message,
    int? orderId,
    String feedbackType = 'ORDER',
  }) async {
    final Map<String, String> headers = await AuthHeaders.getHeaders();

    final Uri url = Uri.parse('${ApiConfig.baseUrl}/feedback');

    final http.Response response = await http.post(
      url,
      headers: headers,
      body: jsonEncode({
        'rating': rating,
        'message': message,
        'order_id': orderId,
        'feedback_type': feedbackType,
      }),
    );

    final dynamic decodedBody =
    response.body.isNotEmpty ? jsonDecode(response.body) : {};

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return decodedBody is Map<String, dynamic>
          ? decodedBody
          : <String, dynamic>{};
    }

    String errorMessage = 'Failed to submit feedback';

    if (decodedBody is Map<String, dynamic> && decodedBody['detail'] != null) {
      errorMessage = decodedBody['detail'].toString();
    }

    throw Exception(errorMessage);
  }
}
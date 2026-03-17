import 'api_client.dart';
import 'token_storage.dart';

class AuthService {
  static Future<Map<String, dynamic>> signup({
    required String fullName,
    String? email,
    String? phone,
    required String password,
  }) async {
    return ApiClient.postJson(
      '/auth/signup',
      auth: false,
      timeout: ApiClient.defaultTimeout,
      body: {
        'full_name': fullName.trim(),
        'email': (email != null && email.trim().isNotEmpty) ? email.trim() : null,
        'phone': (phone != null && phone.trim().isNotEmpty) ? phone.trim() : null,
        'password': password,
      },
    );
  }

  static Future<Map<String, dynamic>> login({
    required String identifier,
    required String password,
  }) async {
    return ApiClient.postJson(
      '/auth/login',
      auth: false,
      timeout: ApiClient.defaultTimeout,
      body: {
        'identifier': identifier.trim(),
        'password': password,
      },
    );
  }

  /////// SINGLE SOURCE OF TRUTH ///////
  static Future<Map<String, dynamic>> me() async {
    // ApiClient will attach token via AuthHeaders.withAuth(...)
    // but we validate token existence early to avoid weird 401 UX.
    final token = await TokenStorage.getToken();
    if (token == null || token.isEmpty) {
      throw const ApiException(statusCode: 401, message: 'Not authenticated');
    }

    return ApiClient.getJson(
      '/auth/me',
      auth: true,
      timeout: ApiClient.defaultTimeout,
      retryOnNetworkError: true,
    );
  }

  /////// UPDATE PROFILE ///////
  static Future<Map<String, dynamic>> updateProfile({
    String? fullName,
    String? email,
    String? deliveryAddress,
  }) async {
    final body = <String, dynamic>{};
    if (fullName != null) body['full_name'] = fullName;
    if (email != null) body['email'] = email;
    if (deliveryAddress != null) body['delivery_address'] = deliveryAddress;

    return ApiClient.patchJson(
      '/auth/me',
      auth: true,
      timeout: ApiClient.defaultTimeout,
      body: body,
    );
  }
}
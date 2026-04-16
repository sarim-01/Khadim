import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'api_config.dart';
import 'auth_headers.dart';

class ApiException implements Exception {
  final int? statusCode;
  final String message;
  final dynamic body;

  const ApiException({this.statusCode, required this.message, this.body});

  bool get isUnauthorized => statusCode == 401;
  bool get isTimeout =>
      statusCode == -1 && message.toLowerCase().contains('timeout');

  @override
  String toString() =>
      'ApiException(statusCode: $statusCode, message: $message)';
}

class ApiClient {
  static String get _base => ApiConfig.baseUrl;

  // Global defaults (can be overridden per request)
  static const Duration defaultTimeout = Duration(seconds: 15);
  static const Duration longTimeout = Duration(seconds: 60);

  /////// PUBLIC METHODS ///////

  static Future<Map<String, dynamic>> getJson(
    String path, {
    bool auth = true,
    Map<String, String>? extraHeaders,
    Duration? timeout,
    bool retryOnNetworkError = true, // safe for GET
  }) async {
    return _request(
      method: 'GET',
      path: path,
      auth: auth,
      extraHeaders: extraHeaders,
      timeout: timeout ?? defaultTimeout,
      retryOnNetworkError: retryOnNetworkError,
    );
  }

  static Future<Map<String, dynamic>> postJson(
    String path, {
    required Map<String, dynamic> body,
    bool auth = true,
    Map<String, String>? extraHeaders,
    Duration? timeout,
  }) async {
    return _request(
      method: 'POST',
      path: path,
      auth: auth,
      extraHeaders: extraHeaders,
      timeout: timeout ?? defaultTimeout,
      body: body,
      retryOnNetworkError: false, // POST not safe by default
    );
  }

  static Future<Map<String, dynamic>> putJson(
    String path, {
    required Map<String, dynamic> body,
    bool auth = true,
    Map<String, String>? extraHeaders,
    Duration? timeout,
  }) async {
    return _request(
      method: 'PUT',
      path: path,
      auth: auth,
      extraHeaders: extraHeaders,
      timeout: timeout ?? defaultTimeout,
      body: body,
      retryOnNetworkError: false,
    );
  }

  static Future<Map<String, dynamic>> patchJson(
    String path, {
    required Map<String, dynamic> body,
    bool auth = true,
    Map<String, String>? extraHeaders,
    Duration? timeout,
  }) async {
    return _request(
      method: 'PATCH',
      path: path,
      auth: auth,
      extraHeaders: extraHeaders,
      timeout: timeout ?? defaultTimeout,
      body: body,
      retryOnNetworkError: false,
    );
  }

  static Future<Map<String, dynamic>> deleteJson(
    String path, {
    bool auth = true,
    Map<String, String>? extraHeaders,
    Duration? timeout,
  }) async {
    return _request(
      method: 'DELETE',
      path: path,
      auth: auth,
      extraHeaders: extraHeaders,
      timeout: timeout ?? defaultTimeout,
      retryOnNetworkError: false,
    );
  }

  /////// CORE REQUEST ///////

  static Future<Map<String, dynamic>> _request({
    required String method,
    required String path,
    required bool auth,
    required Duration timeout,
    Map<String, String>? extraHeaders,
    Map<String, dynamic>? body,
    required bool retryOnNetworkError,
  }) async {
    final uri = Uri.parse("$_base$path");
    final headers =
        await _buildHeaders(auth: auth, json: true, extra: extraHeaders);

    Future<http.Response> doCall() async {
      switch (method) {
        case 'GET':
          return http.get(uri, headers: headers);
        case 'POST':
          return http.post(uri, headers: headers, body: jsonEncode(body ?? {}));
        case 'PUT':
          return http.put(uri, headers: headers, body: jsonEncode(body ?? {}));
        case 'PATCH':
          return http.patch(uri,
              headers: headers, body: jsonEncode(body ?? {}));
        case 'DELETE':
          return http.delete(uri, headers: headers);
        default:
          throw const ApiException(message: 'Unsupported HTTP method');
      }
    }

    try {
      if (!retryOnNetworkError) {
        final res = await doCall().timeout(timeout);
        return _handleResponse(res);
      }

      // GET retry: initial + 1 retry
      try {
        final res = await doCall().timeout(timeout);
        return _handleResponse(res);
      } on SocketException {
        await Future.delayed(const Duration(milliseconds: 350));
        final res = await doCall().timeout(timeout);
        return _handleResponse(res);
      } on TimeoutException {
        await Future.delayed(const Duration(milliseconds: 350));
        final res = await doCall().timeout(timeout);
        return _handleResponse(res);
      }
    } on TimeoutException {
      throw const ApiException(statusCode: -1, message: 'Request timeout');
    } on SocketException {
      throw ApiException(
        statusCode: -2,
        message:
            'Cannot reach backend at ${ApiConfig.baseUrl}. Check backend server and API_BASE_URL.',
      );
    } on HttpException {
      throw const ApiException(statusCode: -3, message: 'HTTP error');
    } on FormatException {
      throw const ApiException(statusCode: -4, message: 'Bad response format');
    } on IOException {
      throw const ApiException(statusCode: -5, message: 'Network I/O error');
    } on ApiException {
      rethrow;
    } catch (e) {
      throw ApiException(
          statusCode: -9, message: 'Unexpected error', body: e.toString());
    }
  }

  static Future<Map<String, String>> _buildHeaders({
    required bool auth,
    required bool json,
    Map<String, String>? extra,
  }) async {
    final base = auth
        ? await AuthHeaders.withAuth(json: json)
        : await AuthHeaders.basic(json: json);

    if (extra == null || extra.isEmpty) return base;

    final merged = <String, String>{};
    merged.addAll(base);
    merged.addAll(extra);
    return merged;
  }

  static Map<String, dynamic> _handleResponse(http.Response res) {
    final status = res.statusCode;

    if (res.body.isEmpty) {
      if (status >= 200 && status < 300) return {};
      throw ApiException(
          statusCode: status, message: 'Request failed', body: null);
    }

    dynamic decoded;
    try {
      decoded = jsonDecode(res.body);
    } catch (_) {
      if (status >= 200 && status < 300) return {"data": res.body};
      throw ApiException(
          statusCode: status, message: 'Request failed', body: res.body);
    }

    if (status >= 200 && status < 300) {
      if (decoded is Map<String, dynamic>) return decoded;
      return {"data": decoded};
    }

    // Common FastAPI shapes:
    // { "detail": "..." } or { "detail": [ ... ] }
    if (decoded is Map && decoded["detail"] != null) {
      final detail = decoded["detail"];
      final msg = detail is String ? detail : 'Request failed';
      throw ApiException(statusCode: status, message: msg, body: decoded);
    }

    // Generic fallback
    throw ApiException(
      statusCode: status,
      message: 'Request failed',
      body: decoded,
    );
  }
}

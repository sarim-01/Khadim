import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class DineInSessionStorage {
  static const FlutterSecureStorage _storage = FlutterSecureStorage();

  static const String _sessionIdKey = 'dine_in_session_id';
  static const String _tableIdKey = 'dine_in_table_id';
  static const String _tableNumberKey = 'dine_in_table_number';
  static const String _tokenKey = 'dine_in_token';

  static Future<void> saveSession({
    required String sessionId,
    required String tableId,
    required String tableNumber,
    String? token,
  }) async {
    await _storage.write(key: _sessionIdKey, value: sessionId);
    await _storage.write(key: _tableIdKey, value: tableId);
    await _storage.write(key: _tableNumberKey, value: tableNumber);
    if (token != null && token.isNotEmpty) {
      await _storage.write(key: _tokenKey, value: token);
    } else {
      await _storage.delete(key: _tokenKey);
    }
  }

  static Future<Map<String, String>?> getSession() async {
    final sessionId = await _storage.read(key: _sessionIdKey);
    final tableId = await _storage.read(key: _tableIdKey);
    final tableNumber = await _storage.read(key: _tableNumberKey);
    final token = await _storage.read(key: _tokenKey);

    if (sessionId == null || tableId == null || tableNumber == null) {
      return null;
    }

    return {
      'session_id': sessionId,
      'table_id': tableId,
      'table_number': tableNumber,
      'token': token ?? '',
    };
  }

  static Future<void> clearSession() async {
    await _storage.delete(key: _sessionIdKey);
    await _storage.delete(key: _tableIdKey);
    await _storage.delete(key: _tableNumberKey);
    await _storage.delete(key: _tokenKey);
  }
}

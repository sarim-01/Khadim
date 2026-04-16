import 'package:flutter/foundation.dart';

class ApiConfig {
  // Highest priority: pass at build/run time.
  // Example:
  // flutter run --dart-define=API_BASE_URL=http://172.17.5.230:8000
  static const String _fromEnv = String.fromEnvironment('API_BASE_URL');

  static String get baseUrl {
    if (_fromEnv.trim().isNotEmpty) {
      return _fromEnv.trim();
    }

    if (kIsWeb) {
      return 'http://localhost:8000';
    }

    // Mobile default: physical devices should use host PC LAN IP.
    // For Android emulator, run with:
    // --dart-define=API_BASE_URL=http://10.0.2.2:8000
    return 'http://192.168.18.10:8000';
  }
}

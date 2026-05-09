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

    // Mobile default: PC Wi‑Fi IPv4 (your IP changes when you switch networks).
    // Override per network: flutter run ... --dart-define=API_BASE_URL=http://...
    // Android emulator: http://10.0.2.2:8000
    return 'http://192.168.18.25:8000';
  }

  /// Paths under `assets/...` are **Flutter bundles**, not URLs on [baseUrl].
  /// Use [flutterBundledAssetPath] and `Image.asset` for those; production APIs
  /// rarely serve `/assets/menu/...`.
  static String? flutterBundledAssetPath(String? raw) {
    if (raw == null) return null;
    var t = raw.trim();
    if (t.isEmpty) return null;
    if (t.startsWith('/assets/')) {
      t = t.substring(1);
    }
    if (t.startsWith('assets/')) {
      return t;
    }
    return null;
  }

  /// Turns API `image_url` values into an absolute URL when the server returns
  /// `/uploads/...`, `uploads/...`, or other app-relative paths (not bundled assets).
  /// Bundled Flutter paths (`assets/...`) return null — use [flutterBundledAssetPath].
  static String? resolvePublicImageUrl(String? raw) {
    if (raw == null) return null;
    final t = raw.trim();
    if (t.isEmpty) return null;
    if (flutterBundledAssetPath(t) != null) {
      return null;
    }
    final base = baseUrl.replaceAll(RegExp(r'/$'), '');
    if (t.startsWith('http://') || t.startsWith('https://')) {
      return t;
    }
    if (t.startsWith('/') && !t.startsWith('/assets/')) {
      return '$base$t';
    }
    // No scheme and not a Flutter asset: treat as path on the API host.
    final path = t.startsWith('/') ? t : '/$t';
    return '$base$path';
  }
}

import 'package:khaadim/services/api_client.dart';

class FavouritesService {
  // ── Toggle (add or remove) ──────────────────────────────────
  static Future<Map<String, dynamic>> toggleFavourite({
    int? itemId,
    int? dealId,
    int? customDealId,
  }) async {
    return ApiClient.postJson(
      '/favourites/toggle',
      auth: true,
      timeout: ApiClient.defaultTimeout,
      body: {
        if (itemId != null) 'item_id': itemId,
        if (dealId != null) 'deal_id': dealId,
        if (customDealId != null) 'custom_deal_id': customDealId,
      },
    );
  }

  // ── Get all favourites (grouped) ───────────────────────────
  static Future<Map<String, dynamic>> getFavourites() async {
    return ApiClient.getJson(
      '/favourites',
      auth: true,
      timeout: ApiClient.defaultTimeout,
      retryOnNetworkError: true,
    );
  }

  // ── Check status for a single entity ──────────────────────
  static Future<Map<String, dynamic>> getFavouriteStatus({
    int? itemId,
    int? dealId,
    int? customDealId,
  }) async {
    final params = <String, String>{};
    if (itemId != null) params['item_id'] = itemId.toString();
    if (dealId != null) params['deal_id'] = dealId.toString();
    if (customDealId != null) {
      params['custom_deal_id'] = customDealId.toString();
    }
    final query = params.entries.map((e) => '${e.key}=${e.value}').join('&');
    return ApiClient.getJson(
      '/favourites/status${query.isNotEmpty ? '?$query' : ''}',
      auth: true,
      timeout: ApiClient.defaultTimeout,
      retryOnNetworkError: true,
    );
  }

  // Voice helper endpoint compatibility for command execution.
  static Future<Map<String, dynamic>> manageVoiceFavourites({
    required String action,
    required String itemName,
    required String language,
  }) async {
    return ApiClient.postJson(
      '/voice/favourites',
      auth: true,
      timeout: ApiClient.defaultTimeout,
      body: {
        'action': action,
        'item_name': itemName,
        'language': language,
      },
    );
  }
}

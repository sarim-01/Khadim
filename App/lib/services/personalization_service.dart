// Phase 4 - Personalization Flutter UI
import 'package:khaadim/models/recommendation_result.dart';
import 'package:khaadim/services/api_client.dart';

class PersonalizationService {
  /// Fetch personalized recommendations for the current user.
  /// Returns [RecommendationResult.empty()] on any error — never throws.
  static Future<RecommendationResult> getRecommendations({
    int topK = 10,
  }) async {
    try {
      final res = await ApiClient.getJson(
        '/personalization/recommendations?top_k=$topK',
        auth: true,
        timeout: const Duration(seconds: 20),
      );
      return RecommendationResult.fromJson(res);
    } catch (_) {
      // Silent fail — home screen must never crash due to personalization
      return RecommendationResult.empty();
    }
  }
}

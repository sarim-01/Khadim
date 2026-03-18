// Phase 4 - Personalization Flutter UI

class RecommendedItem {
  final int itemId;
  final String itemName;
  final double score;
  final String reason;
  final String source;
  final String category;

  const RecommendedItem({
    required this.itemId,
    required this.itemName,
    required this.score,
    required this.reason,
    required this.source,
    required this.category,
  });

  factory RecommendedItem.fromJson(Map<String, dynamic> json) {
    return RecommendedItem(
      itemId: (json['item_id'] as num?)?.toInt() ?? 0,
      itemName: json['item_name'] as String? ?? '',
      score: (json['score'] as num?)?.toDouble() ?? 0,
      reason: json['reason'] as String? ?? '',
      source: json['source'] as String? ?? '',
      category: json['category'] as String? ?? 'fast_food',
    );
  }
}

class RecommendedDeal {
  final int dealId;
  final String dealName;
  final double score;
  final String reason;
  final String source;
  final String category;
  final String items;

  const RecommendedDeal({
    required this.dealId,
    required this.dealName,
    required this.score,
    required this.reason,
    required this.source,
    required this.category,
    required this.items,
  });

  factory RecommendedDeal.fromJson(Map<String, dynamic> json) {
    return RecommendedDeal(
      dealId: (json['deal_id'] as num?)?.toInt() ?? 0,
      dealName: json['deal_name'] as String? ?? '',
      score: (json['score'] as num?)?.toDouble() ?? 0,
      reason: json['reason'] as String? ?? '',
      source: json['source'] as String? ?? '',
      category: json['category'] as String? ?? 'fast_food',
      items: json['items'] as String? ?? '',
    );
  }
}

class RecommendationResult {
  final List<RecommendedItem> recommendedItems;
  final List<RecommendedDeal> recommendedDeals;
  final String source;
  final bool fromCache;
  final String generatedAt;

  const RecommendationResult({
    required this.recommendedItems,
    required this.recommendedDeals,
    required this.source,
    required this.fromCache,
    required this.generatedAt,
  });

  factory RecommendationResult.empty() => const RecommendationResult(
        recommendedItems: [],
        recommendedDeals: [],
        source: '',
        fromCache: false,
        generatedAt: '',
      );

  factory RecommendationResult.fromJson(Map<String, dynamic> json) {
    final items = (json['recommended_items'] as List? ?? [])
        .whereType<Map<String, dynamic>>()
        .map(RecommendedItem.fromJson)
        .toList();

    final deals = (json['recommended_deals'] as List? ?? [])
        .whereType<Map<String, dynamic>>()
        .map(RecommendedDeal.fromJson)
        .toList();

    return RecommendationResult(
      recommendedItems: items,
      recommendedDeals: deals,
      source: json['source'] as String? ?? '',
      fromCache: json['from_cache'] as bool? ?? false,
      generatedAt: json['generated_at'] as String? ?? '',
    );
  }
}

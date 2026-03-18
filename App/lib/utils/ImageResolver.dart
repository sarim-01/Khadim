class ImageResolver {
  // Category folder paths
  static const Map<String, String> categoryFolders = {
    "bbq": "assets/images/menu/bbq/",
    "bread": "assets/images/menu/bread/",
    "chinese": "assets/images/menu/chinese/",
    "desi": "assets/images/menu/desi/",
    "drinks": "assets/images/menu/drinks/",
    "fast_food": "assets/images/menu/fast_food/",
  };

  // Deal banner images
  static const Map<String, String> dealImages = {
    "bbq": "assets/images/deals/deal_bbq.jpeg",
    "chinese": "assets/images/deals/deal_chinese.jpeg",
    "desi": "assets/images/deals/deal_desi.jpeg",
    "drinks": "assets/images/deals/deal_drinks.jpeg",
    "fast_food": "assets/images/deals/deal_fastfood.jpeg",
  };

  // Fallback image (in case item not found)
  static const String fallbackImage = "assets/images/confirm.png";

  // Convert item name → filename
  static String normalizeItemName(String itemName) {
    return itemName
        .trim()
        .toLowerCase()
        .replaceAll(" ", "_")
        .replaceAll("-", "_");
  }

  // MAIN FUNCTION: Get menu image asset path
  static String getMenuImage(String category, String itemName) {
    final folder = categoryFolders[category.toLowerCase()];
    if (folder == null) return fallbackImage;

    final normalized = normalizeItemName(itemName);
    final path = "$folder$normalized.jpeg";

    return path;
  }

  // Get deal banner
  static String getDealImage(String dealName) {
    return dealImages[getDealCategory(dealName)] ?? fallbackImage;
  }

  // Guess deal category from name
  static String getDealCategory(String dealName) {
    final name = dealName.toLowerCase();
    if (name.contains("fast")) return "fast_food";
    if (name.contains("bbq")) return "bbq";
    if (name.contains("chinese")) return "chinese";
    if (name.contains("desi")) return "desi";
    if (name.contains("drink")) return "drinks";
    return "fast_food";
  }
}

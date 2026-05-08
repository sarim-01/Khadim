class ImageResolver {
  /// Checked first: alternate spellings / legacy filenames used by the menu UI.
  /// Paths must match real files under [assets/images/menu/].
  static const Map<String, String> menuUiAliases = {
    'Burger': 'assets/images/menu/fast_food/cheeseburger.png',
    'Chicken Burger': 'assets/images/menu/fast_food/chicken_burger.png',
    'Fries': 'assets/images/menu/fast_food/fries.jpeg',
    'Loaded Fries': 'assets/images/menu/fast_food/loaded_fries.jpeg',
    'Nuggets': 'assets/images/menu/fast_food/chicken nuggets.png',
    'Beef Boti': 'assets/images/menu/bbq/beef_boti.jpeg',
    'Chicken Tikka': 'assets/images/menu/bbq/chicken_tikka.jpeg',
    'Grilled Fish': 'assets/images/menu/bbq/grilled_fish.jpeg',
    'Malai Boti': 'assets/images/menu/bbq/malai_boti.jpeg',
    'Reshmi Kebab': 'assets/images/menu/bbq/reshmi_kebab.jpeg',
    'Garlic Naan': 'assets/images/menu/bread/garlic_naan.jpeg',
    'Naan': 'assets/images/menu/bread/naan.jpeg',
    'Paratha': 'assets/images/menu/bread/paratha.jpeg',
    'Roti': 'assets/images/menu/bread/roti.jpeg',
    'Chow Mein': 'assets/images/menu/chinese/chicken chow mein.png',
    'Hot Sour Soup': 'assets/images/menu/chinese/hot and sour soup.png',
    'Kung Pao': 'assets/images/menu/chinese/kung pao chicken.png',
    'Manchurian': 'assets/images/menu/chinese/chicken manchurian.png',
    'Spring Rolls': 'assets/images/menu/chinese/vagetable spring rolls.png',
    'Biryani': 'assets/images/menu/desi/biryani.jpeg',
    'Chana Chaat': 'assets/images/menu/desi/chana_chaat.jpeg',
    'Chicken Karahi': 'assets/images/menu/desi/chicken_karahi.jpeg',
    'Daal Chawal': 'assets/images/menu/desi/daal_chawal.jpeg',
    'Nihari': 'assets/images/menu/desi/nihari.jpeg',
    'Samosa': 'assets/images/menu/desi/samosa.jpeg',
    'Chai': 'assets/images/menu/drinks/chai.jpeg',
    'Cola': 'assets/images/menu/drinks/cola.jpg',
    'Iced Coffee': 'assets/images/menu/drinks/iced_coffee.jpeg',
    'Lemonade': 'assets/images/menu/drinks/lemonade.jpeg',
    'Mint Margarita': 'assets/images/menu/drinks/mint_margarita.jpeg',
  };

  // Keys match EXACT item_name values from the database.
  static const Map<String, String> exactMenuImages = {

    // ── FAST FOOD (items 1-10) ────────────────────────────────
    "Cheeseburger":           "assets/images/menu/fast_food/cheeseburger.png",
    "Chicken Burger":         "assets/images/menu/fast_food/chicken_burger.png",
    "Veggie Burger":          "assets/images/menu/fast_food/veggie burger.png",
    "Fries":                  "assets/images/menu/fast_food/fries.jpeg",
    "Chicken Nuggets":        "assets/images/menu/fast_food/chicken nuggets.png",
    "Fish Fillet Sandwich":   "assets/images/menu/fast_food/fish fillet sandwich.png",
    "Onion Rings":            "assets/images/menu/fast_food/onion rings.png",
    "Club Sandwich":          "assets/images/menu/fast_food/club sandwich.png",
    "Zinger Burger":          "assets/images/menu/fast_food/zinger burger.png",
    "Loaded Fries":           "assets/images/menu/fast_food/loaded_fries.jpeg",

    // ── CHINESE (items 11-20) ─────────────────────────────────
    "Kung Pao Chicken":           "assets/images/menu/chinese/kung pao chicken.png",
    "Sweet and Sour Chicken":     "assets/images/menu/chinese/sweet and sour chicken.png",
    "Chicken Chow Mein":          "assets/images/menu/chinese/chicken chow mein.png",
    "Vegetable Spring Rolls":     "assets/images/menu/chinese/vagetable spring rolls.png",
    "Beef with Black Bean Sauce": "assets/images/menu/chinese/beef with black bean sauce.png",
    "Egg Fried Rice":             "assets/images/menu/chinese/egg fried rice.png",
    "Hot and Sour Soup":          "assets/images/menu/chinese/hot and sour soup.png",
    "Szechuan Beef":              "assets/images/menu/chinese/beef szechuan.png",
    "Chicken Manchurian":         "assets/images/menu/chinese/chicken manchurian.png",
    "Fish Crackers":              "assets/images/menu/chinese/fish crackers.png",

    // ── DESI (items 21-30) ────────────────────────────────────
    "Chicken Karahi":  "assets/images/menu/desi/chicken_karahi.jpeg",
    "Beef Biryani":    "assets/images/menu/desi/beef biryani.png",
    "Daal Chawal":     "assets/images/menu/desi/daal_chawal.jpeg",
    "Nihari":          "assets/images/menu/desi/nihari.jpeg",
    "Aloo Paratha":    "assets/images/menu/desi/Aloo Paratha.png",
    "Palak Paneer":    "assets/images/menu/desi/palak paneer.png",
    "Chana Chaat":     "assets/images/menu/desi/chana_chaat.jpeg",
    "Samosa Platter":  "assets/images/menu/desi/samosa platter.png",
    "Seekh Kabab":     "assets/images/menu/desi/Seekh kabab.png",
    "Chicken Handi":   "assets/images/menu/desi/Chicken Handi.png",

    // ── BBQ (items 31-35) ─────────────────────────────────────
    "Chicken Tikka":  "assets/images/menu/bbq/chicken_tikka.jpeg",
    "Beef Boti":      "assets/images/menu/bbq/beef_boti.jpeg",
    "Malai Boti":     "assets/images/menu/bbq/malai_boti.jpeg",
    "Reshmi Kebab":   "assets/images/menu/bbq/reshmi_kebab.jpeg",
    "Grilled Fish":   "assets/images/menu/bbq/grilled_fish.jpeg",

    // ── DRINKS (items 36-44) ──────────────────────────────────
    "Cola":             "assets/images/menu/drinks/cola.jpg",
    "Lemonade":         "assets/images/menu/drinks/lemonade.jpeg",
    "Mint Margarita":   "assets/images/menu/drinks/mint_margarita.jpeg",
    "Green Tea":        "assets/images/menu/drinks/green tea.png",
    "Chai":             "assets/images/menu/drinks/chai.jpeg",
    "Iced Coffee":      "assets/images/menu/drinks/iced_coffee.jpeg",
    "Strawberry Shake": "assets/images/menu/drinks/strawberry shake.png",
    "Orange Juice":     "assets/images/menu/drinks/orange juice.png",
    "Water Bottle":     "assets/images/menu/drinks/Mineral water.png",

    // ── BREAD (items 45-49) ───────────────────────────────────
    "Roti":        "assets/images/menu/bread/roti.jpeg",
    "Naan":        "assets/images/menu/bread/naan.jpeg",
    "Garlic Naan": "assets/images/menu/bread/garlic_naan.jpeg",
    "Paratha":     "assets/images/menu/bread/paratha.jpeg",
    "Chapatti":    "assets/images/menu/desi/chapati.png",
  };

  // Category folder paths (normalised-name fallback)
  static const Map<String, String> categoryFolders = {
    "bbq":       "assets/images/menu/bbq/",
    "bread":     "assets/images/menu/bread/",
    "chinese":   "assets/images/menu/chinese/",
    "desi":      "assets/images/menu/desi/",
    "drinks":    "assets/images/menu/drinks/",
    "fast_food": "assets/images/menu/fast_food/",
  };

  // Deal images — keys match exact deal_name values from the database.
  static const Map<String, String> exactDealImages = {
    // BBQ
    "BBQ Solo":    "assets/images/deals/BBQ deals/bbq_solo.png",
    "BBQ Duo":     "assets/images/deals/BBQ deals/bbq duo.png",
    "BBQ Squad":   "assets/images/deals/BBQ deals/bbq_squad.png",
    "BBQ Party A": "assets/images/deals/BBQ deals/bbq_party_A.png",
    "BBQ Party B": "assets/images/deals/BBQ deals/bbq_party_B.png",
    // Chinese
    "Chinese Solo":          "assets/images/deals/Chinese Deals/chinese_solo.png",
    "Chinese Duo":           "assets/images/deals/Chinese Deals/chinese_duo.png",
    "Chinese Squad A":       "assets/images/deals/Chinese Deals/chinese_squad_A.png",
    "Chinese Squad B":       "assets/images/deals/Chinese Deals/Chinese_Squad_B.png",
    "Chinese Party Variety": "assets/images/deals/Chinese Deals/chinese_party.png",
    // Desi
    "Desi Solo":    "assets/images/deals/Desi deals/desi_solo.png",
    "Desi Duo":     "assets/images/deals/Desi deals/desi_duo.png",
    "Desi Squad A": "assets/images/deals/Desi deals/desi_squad_A.png",
    "Desi Squad B": "assets/images/deals/Desi deals/desi_squad_B.png",
    "Desi Party":   "assets/images/deals/Desi deals/desi_party.png",  
    // Fast Food
    "Fast Solo A":        "assets/images/deals/FastFood deals/Fast_solo_A.png",
    "Fast Solo B":        "assets/images/deals/FastFood deals/Fast_solo_B.png",
    "Fast Duo":           "assets/images/deals/FastFood deals/Fast_Duo.png",
    "Fast Squad":         "assets/images/deals/FastFood deals/Fast_squad.png",
    "Fast Food Big Party":"assets/images/deals/FastFood deals/Fast_food_big_party.png",
  };

  // Legacy category-based deal banners (kept for any other callers)
  static const Map<String, String> dealImages = {
    "bbq":       "assets/images/deals/BBQ deals/bbq_solo.png",
    "chinese":   "assets/images/deals/Chinese Deals/chinese_solo.png",
    "desi":      "assets/images/deals/Desi deals/desi_solo.png",
    "drinks":    "assets/images/confirm.png",
    "fast_food": "assets/images/deals/FastFood deals/Fast_solo_A.png",
  };

  static const String fallbackImage = "assets/images/confirm.png";

  static String? _findCaseInsensitive(Map<String, String> map, String key) {
    final lookup = key.trim().toLowerCase();
    for (final entry in map.entries) {
      if (entry.key.toLowerCase() == lookup) {
        return entry.value;
      }
    }
    return null;
  }

  static String normalizeItemName(String itemName) {
    return itemName
        .trim()
        .toLowerCase()
        .replaceAll(" ", "_")
        .replaceAll("-", "_");
  }

  /// Maps [item_cuisine] from the API to the keys used in [getMenuImage] fallbacks.
  static String normalizeCuisineForMenuImage(String itemCuisine) {
    final key = itemCuisine
        .trim()
        .toLowerCase()
        .replaceAll(RegExp(r'[\s\-]+'), '_')
        .replaceAll(RegExp(r'_+'), '_');
    switch (key) {
      case 'fastfood':
        return 'fast_food';
      case 'barbeque':
      case 'barbecue':
        return 'bbq';
      case 'beverages':
      case 'beverage':
        return 'drinks';
      default:
        return key;
    }
  }

  // 1. UI aliases → 2. Exact DB name → 3. Category fallback → 4. Placeholder
  static String getMenuImage(String category, String itemName) {
    final trimmed = itemName.trim();
    final fromAlias = menuUiAliases[trimmed] ??
        _findCaseInsensitive(menuUiAliases, itemName);
    if (fromAlias != null) return fromAlias;

    final exact = exactMenuImages[trimmed] ??
        _findCaseInsensitive(exactMenuImages, itemName);
    if (exact != null) return exact;

    switch (normalizeCuisineForMenuImage(category)) {
      case 'bbq':
        return 'assets/images/menu/bbq/chicken_tikka.jpeg';
      case 'bread':
        return 'assets/images/menu/bread/roti.jpeg';
      case 'chinese':
        return 'assets/images/menu/chinese/kung pao chicken.png';
      case 'desi':
        return 'assets/images/menu/desi/chicken_karahi.jpeg';
      case 'drinks':
        return 'assets/images/menu/drinks/cola.jpg';
      case 'fast_food':
        return 'assets/images/confirm.png';
      default:
        return fallbackImage;
    }
  }

  static String getDealImage(String dealName) {
    // 1. Exact match by deal name
    final exact = exactDealImages[dealName.trim()] ??
        _findCaseInsensitive(exactDealImages, dealName);
    if (exact != null) return exact;
    // 2. Legacy category fallback
    return dealImages[getDealCategory(dealName)] ?? fallbackImage;
  }

  static String getDealCategory(String dealName) {
    final name = dealName.toLowerCase();
    if (name.contains("fast"))    return "fast_food";
    if (name.contains("bbq"))     return "bbq";
    if (name.contains("chinese")) return "chinese";
    if (name.contains("desi"))    return "desi";
    if (name.contains("drink"))   return "drinks";
    return "fast_food";
  }
}

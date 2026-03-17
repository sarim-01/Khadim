/// Model for items within a custom deal
class CustomDealItem {
  final int itemId;
  final String itemName;
  final double price;
  final int quantity;
  final String itemType;

  CustomDealItem({
    required this.itemId,
    required this.itemName,
    required this.price,
    required this.quantity,
    this.itemType = 'menu_item',
  });

  factory CustomDealItem.fromJson(Map<String, dynamic> json) {
    return CustomDealItem(
      itemId: json['item_id'] ?? 0,
      itemName: json['item_name'] ?? '',
      price: (json['price'] ?? json['item_price'] ?? 0).toDouble(),
      quantity: json['quantity'] ?? 1,
      itemType: json['item_type'] ?? 'menu_item',
    );
  }

  Map<String, dynamic> toJson() => {
    'item_id': itemId,
    'item_name': itemName,
    'price': price,
    'item_price': price,
    'quantity': quantity,
    'item_type': itemType,
  };
}

/// Model for a custom deal response from the API
class CustomDealResponse {
  final bool success;
  final String message;
  final List<CustomDealItem> items;
  final double totalPrice;

  CustomDealResponse({
    required this.success,
    required this.message,
    this.items = const [],
    this.totalPrice = 0,
  });

  factory CustomDealResponse.fromJson(Map<String, dynamic> json) {
    final List<CustomDealItem> parsedItems =
    (json['items'] as List<dynamic>? ?? [])
        .map((e) => CustomDealItem.fromJson(e as Map<String, dynamic>))
        .toList();

    final double parsedTotalPrice =
    (json['total_price'] ?? 0).toDouble();

    return CustomDealResponse(
      success: json['success'] ?? false,
      message: json['message'] ?? '',
      items: parsedItems,
      totalPrice: parsedTotalPrice,
    );
  }

  bool get hasItems => items.isNotEmpty;
}
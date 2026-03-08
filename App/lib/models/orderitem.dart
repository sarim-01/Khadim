class OrderItem {
  final String id;
  final String itemType;
  final int itemId;
  final String name;
  final int quantity;
  final double unitPrice;
  final double lineTotal;

  const OrderItem({
    required this.id,
    required this.itemType,
    required this.itemId,
    required this.name,
    required this.quantity,
    required this.unitPrice,
    required this.lineTotal,
  });

  factory OrderItem.fromJson(Map<String, dynamic> json) {
    final quantityValue = json['quantity'];
    final unitPriceValue = json['unit_price'] ?? json['unit_price_snapshot'] ?? 0;
    final lineTotalValue = json['line_total'] ?? 0;

    return OrderItem(
      id: json['id']?.toString() ?? '',
      itemType: json['item_type']?.toString() ?? '',
      itemId: (json['item_id'] is num) ? (json['item_id'] as num).toInt() : 0,
      name: json['name']?.toString() ??
          json['name_snapshot']?.toString() ??
          '',
      quantity: (quantityValue is num) ? quantityValue.toInt() : 0,
      unitPrice: (unitPriceValue is num) ? unitPriceValue.toDouble() : 0.0,
      lineTotal: (lineTotalValue is num) ? lineTotalValue.toDouble() : 0.0,
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'item_type': itemType,
    'item_id': itemId,
    'name': name,
    'quantity': quantity,
    'unit_price': unitPrice,
    'line_total': lineTotal,
  };
}
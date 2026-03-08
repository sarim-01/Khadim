import 'orderitem.dart';

class Order {
  final int orderId;
  final String cartId;
  final String status;
  final double totalPrice;
  final double subtotal;
  final double tax;
  final double deliveryFee;
  final int estimatedPrepTimeMinutes;
  final String deliveryAddress;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final List<OrderItem> items;

  const Order({
    required this.orderId,
    required this.cartId,
    required this.status,
    required this.totalPrice,
    required this.subtotal,
    required this.tax,
    required this.deliveryFee,
    required this.estimatedPrepTimeMinutes,
    required this.deliveryAddress,
    required this.createdAt,
    required this.updatedAt,
    required this.items,
  });

  String get orderNumber => orderId.toString();

  factory Order.fromJson(Map<String, dynamic> json) {
    return Order(
      orderId: (json['order_id'] is num) ? (json['order_id'] as num).toInt() : 0,
      cartId: json['cart_id']?.toString() ?? '',
      status: json['status']?.toString() ?? '',
      totalPrice: (json['total_price'] is num)
          ? (json['total_price'] as num).toDouble()
          : ((json['total'] is num) ? (json['total'] as num).toDouble() : 0.0),
      subtotal: (json['subtotal'] is num) ? (json['subtotal'] as num).toDouble() : 0.0,
      tax: (json['tax'] is num) ? (json['tax'] as num).toDouble() : 0.0,
      deliveryFee: (json['delivery_fee'] is num)
          ? (json['delivery_fee'] as num).toDouble()
          : 0.0,
      estimatedPrepTimeMinutes: (json['estimated_prep_time_minutes'] is num)
          ? (json['estimated_prep_time_minutes'] as num).toInt()
          : 0,
      deliveryAddress: json['delivery_address']?.toString() ?? '',
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'].toString())
          : null,
      updatedAt: json['updated_at'] != null
          ? DateTime.tryParse(json['updated_at'].toString())
          : null,
      items: (json['items'] as List? ?? [])
          .map((e) => OrderItem.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
    );
  }
}
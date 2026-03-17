import 'package:flutter/material.dart';
import 'package:khaadim/models/order.dart';
import 'package:khaadim/screens/orders/order_tracking_screen.dart';
import 'package:khaadim/services/order_service.dart';
import 'package:khaadim/screens/support/feedback_screen.dart';

class OrderHistoryScreen extends StatefulWidget {
  const OrderHistoryScreen({super.key});

  @override
  State<OrderHistoryScreen> createState() => _OrderHistoryScreenState();
}

class _OrderHistoryScreenState extends State<OrderHistoryScreen> {
  bool _loading = true;
  String? _error;
  List<Order> _orders = [];

  @override
  void initState() {
    super.initState();
    _loadOrders();
  }

  Future<void> _loadOrders() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final res = await OrderService.getMyOrders();
      final rawOrders = (res["orders"] as List? ?? []);

      _orders = rawOrders
          .map((e) => Order.fromJson(Map<String, dynamic>.from(e)))
          .toList();
    } catch (e) {
      _error = e.toString().replaceFirst('Exception: ', '');
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  String _formatDate(DateTime? dt) {
    if (dt == null) return "Unknown time";
    return "${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} "
        "${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}";
  }

  bool _isDelivered(String status) {
    final s = status.toLowerCase();
    return s == "completed" || s == "delivered";
  }

  Color _statusColor(String status, ColorScheme color) {
    switch (status.toLowerCase()) {
      case 'confirmed':
        return Colors.blueGrey;
      case 'in_kitchen':
        return Colors.orange;
      case 'preparing':
        return Colors.amber;
      case 'ready':
        return Colors.green;
      case 'completed':
      case 'delivered':
        return Colors.green.shade700;
      default:
        return color.primary;
    }
  }

  String _statusLabel(String status) {
    switch (status.toLowerCase()) {
      case 'confirmed':
        return 'Confirmed';
      case 'in_kitchen':
        return 'In Kitchen';
      case 'preparing':
        return 'Preparing';
      case 'ready':
        return 'Ready';
      case 'completed':
        return 'Completed';
      case 'delivered':
        return 'Delivered';
      default:
        return status;
    }
  }

  Future<void> _openFeedback(Order order) async {
    final result = await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => FeedbackScreen(
          orderId: order.orderId,
          feedbackType: 'ORDER',
        ),
      ),
    );

    if (result == true) {
      _loadOrders();
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = theme.colorScheme;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Order History'),
        actions: [
          IconButton(
            onPressed: _loading ? null : _loadOrders,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
          ? Center(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Text(
            _error!,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyMedium,
          ),
        ),
      )
          : _orders.isEmpty
          ? const Center(child: Text("No orders found"))
          : ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: _orders.length,
        itemBuilder: (context, index) {
          final order = _orders[index];
          final delivered = _isDelivered(order.status);

          return Card(
            color: theme.cardColor,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
            ),
            margin: const EdgeInsets.only(bottom: 12),
            child: InkWell(
              borderRadius: BorderRadius.circular(10),
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => OrderTrackingScreen(
                      orderId: order.orderId,
                    ),
                  ),
                );
              },
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  vertical: 12,
                  horizontal: 12,
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment:
                        CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Order #${order.orderNumber}',
                            style: theme.textTheme.titleSmall
                                ?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: color.onBackground,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'Placed on ${_formatDate(order.createdAt)}',
                            style: theme.textTheme.bodySmall
                                ?.copyWith(
                              color: theme.hintColor,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 3,
                            ),
                            decoration: BoxDecoration(
                              color: _statusColor(
                                order.status,
                                color,
                              ).withOpacity(0.15),
                              borderRadius:
                              BorderRadius.circular(20),
                              border: Border.all(
                                color: _statusColor(
                                  order.status,
                                  color,
                                ),
                                width: 1,
                              ),
                            ),
                            child: Text(
                              _statusLabel(order.status),
                              style: theme.textTheme.bodySmall
                                  ?.copyWith(
                                color: _statusColor(
                                  order.status,
                                  color,
                                ),
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          'Rs ${order.totalPrice.toStringAsFixed(2)}',
                          style: theme.textTheme.bodyLarge
                              ?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: color.primary,
                          ),
                        ),
                        const SizedBox(height: 8),
                        if (delivered)
                          SizedBox(
                            height: 32,
                            child: OutlinedButton(
                              onPressed: () => _openFeedback(order),
                              style: OutlinedButton.styleFrom(
                                side: BorderSide(
                                  color: color.primary,
                                ),
                                foregroundColor: color.primary,
                                padding:
                                const EdgeInsets.symmetric(
                                  horizontal: 10,
                                ),
                              ),
                              child: const Text('Feedback'),
                            ),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
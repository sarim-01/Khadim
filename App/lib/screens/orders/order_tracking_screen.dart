import 'package:flutter/material.dart';
import 'package:khaadim/models/order.dart';
import 'package:khaadim/screens/orders/order_history_screen.dart';
import 'package:khaadim/services/order_service.dart';

class OrderTrackingScreen extends StatefulWidget {
  final int orderId;

  const OrderTrackingScreen({
    super.key,
    required this.orderId,
  });

  @override
  State<OrderTrackingScreen> createState() => _OrderTrackingScreenState();
}

class _OrderTrackingScreenState extends State<OrderTrackingScreen> {
  bool _loading = true;
  String? _error;
  Order? _order;

  @override
  void initState() {
    super.initState();
    _loadOrder();
  }

  Future<void> _loadOrder() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final res = await OrderService.getOrderDetail(orderId: widget.orderId);
      final rawOrder = Map<String, dynamic>.from(res["order"] ?? {});
      _order = Order.fromJson(rawOrder);
    } catch (e) {
      _error = e.toString();
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  double _progressForStatus(String status) {
    final s = status.toLowerCase();

    switch (s) {
      case 'created':
        return 0.15;
      case 'confirmed':
        return 0.25;
      case 'in_kitchen':
        return 0.45;
      case 'preparing':
        return 0.65;
      case 'ready':
        return 0.85;
      case 'completed':
        return 1.0;
      default:
        return 0.2;
    }
  }

  bool _isDone(String currentStatus, List<String> states) {
    final status = currentStatus.toLowerCase();
    return states.contains(status);
  }

  bool _isCurrent(String currentStatus, List<String> states) {
    return states.contains(currentStatus.toLowerCase());
  }

  Widget _buildStatusRow(
      BuildContext context, {
        required IconData icon,
        required String title,
        required bool done,
        required bool inProgress,
      }) {
    final theme = Theme.of(context);
    final color = theme.colorScheme;

    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Icon(
        icon,
        color: done
            ? Colors.green
            : inProgress
            ? color.primary
            : theme.hintColor,
      ),
      title: Text(
        title,
        style: theme.textTheme.bodyMedium?.copyWith(
          fontWeight: FontWeight.w500,
          color: done
              ? Colors.green
              : inProgress
              ? color.primary
              : theme.hintColor,
        ),
      ),
      trailing: done
          ? const Icon(Icons.check, color: Colors.green)
          : inProgress
          ? Text(
        'In Progress',
        style: theme.textTheme.bodySmall?.copyWith(
          color: color.primary,
        ),
      )
          : null,
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = theme.colorScheme;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Track Order'),
        actions: [
          IconButton(
            onPressed: _loading ? null : _loadOrder,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: color.primary,
        foregroundColor: color.onPrimary,
        onPressed: () {},
        child: const Icon(Icons.mic_none_rounded),
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
          ),
        ),
      )
          : _order == null
          ? const Center(child: Text("Order not found"))
          : SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Card(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 20,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Order #${_order!.orderNumber}',
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Estimated Prep Time',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.hintColor,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        Icon(Icons.access_time,
                            color: color.primary, size: 18),
                        const SizedBox(width: 6),
                        Text(
                          _order!.estimatedPrepTimeMinutes > 0
                              ? '${_order!.estimatedPrepTimeMinutes} mins'
                              : 'Updating',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            fontWeight: FontWeight.w500,
                            color: color.primary,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    LinearProgressIndicator(
                      value: _progressForStatus(_order!.status),
                      backgroundColor:
                      color.primary.withOpacity(0.2),
                      color: color.primary,
                      minHeight: 4,
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'Status: ${_order!.status}',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: color.primary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 20),
            Card(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 16,
                ),
                child: Column(
                  children: [
                    _buildStatusRow(
                      context,
                      icon: Icons.check_circle,
                      title: 'Order Confirmed',
                      done: _isDone(_order!.status, [
                        'confirmed',
                        'in_kitchen',
                        'preparing',
                        'ready',
                        'completed'
                      ]),
                      inProgress: _isCurrent(_order!.status, ['confirmed']),
                    ),
                    _buildStatusRow(
                      context,
                      icon: Icons.restaurant_menu,
                      title: 'In Kitchen',
                      done: _isDone(_order!.status, [
                        'in_kitchen',
                        'preparing',
                        'ready',
                        'completed'
                      ]),
                      inProgress: _isCurrent(_order!.status, ['in_kitchen']),
                    ),
                    _buildStatusRow(
                      context,
                      icon: Icons.local_fire_department,
                      title: 'Preparing',
                      done: _isDone(_order!.status, [
                        'preparing',
                        'ready',
                        'completed'
                      ]),
                      inProgress: _isCurrent(_order!.status, ['preparing']),
                    ),
                    _buildStatusRow(
                      context,
                      icon: Icons.done_all,
                      title: 'Ready / Completed',
                      done: _isDone(_order!.status, ['ready', 'completed']),
                      inProgress: _isCurrent(_order!.status, ['ready']),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 20),
            Card(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 16,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Order Items',
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 12),
                    ..._order!.items.map(
                          (item) => Padding(
                        padding: const EdgeInsets.only(bottom: 10),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Text(
                                '${item.name} x${item.quantity}',
                                style: theme.textTheme.bodyMedium,
                              ),
                            ),
                            Text(
                              'Rs ${item.lineTotal.toStringAsFixed(2)}',
                              style: theme.textTheme.bodyMedium?.copyWith(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const Divider(),
                    Row(
                      mainAxisAlignment:
                      MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Subtotal',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: theme.hintColor,
                          ),
                        ),
                        Text(
                          'Rs ${_order!.subtotal.toStringAsFixed(2)}',
                          style: theme.textTheme.bodyMedium,
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Row(
                      mainAxisAlignment:
                      MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Tax',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: theme.hintColor,
                          ),
                        ),
                        Text(
                          'Rs ${_order!.tax.toStringAsFixed(2)}',
                          style: theme.textTheme.bodyMedium,
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Row(
                      mainAxisAlignment:
                      MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Delivery Fee',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: theme.hintColor,
                          ),
                        ),
                        Text(
                          'Rs ${_order!.deliveryFee.toStringAsFixed(2)}',
                          style: theme.textTheme.bodyMedium,
                        ),
                      ],
                    ),
                    const Divider(),
                    Row(
                      mainAxisAlignment:
                      MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Total',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        Text(
                          'Rs ${_order!.totalPrice.toStringAsFixed(2)}',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: color.primary,
                          ),
                        ),
                      ],
                    ),
                    if (_order!.deliveryAddress.isNotEmpty) ...[
                      const SizedBox(height: 16),
                      Text(
                        'Delivery Address',
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        _order!.deliveryAddress,
                        style: theme.textTheme.bodyMedium,
                      ),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () {
                  Navigator.pushReplacement(
                    context,
                    MaterialPageRoute(
                      builder: (_) => const OrderHistoryScreen(),
                    ),
                  );
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: color.primary,
                  foregroundColor: color.onPrimary,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
                child: const Text('View Order History'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
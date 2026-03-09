import 'dart:async';
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
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _loadOrder();
    // Start polling every 5 seconds after the first full load
    _pollTimer = Timer.periodic(const Duration(seconds: 5), (_) => _pollStatus());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  /// Full reload — called on initState and manual refresh button.
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

  /// Lightweight poll — only updates status + prep time. Does NOT rebuild the full order.
  Future<void> _pollStatus() async {
    if (_order == null) return;
    try {
      final res = await OrderService.getOrderTracking(orderId: widget.orderId);
      final newStatus = (res['status'] as String?)?.toLowerCase() ?? _order!.status;
      final newPrepTime = (res['estimated_prep_time_minutes'] as num?)?.toInt() ?? _order!.estimatedPrepTimeMinutes;

      if (!mounted) return;

      final statusChanged = newStatus != _order!.status;
      setState(() {
        _order = _order!.copyWith(
          status: newStatus,
          estimatedPrepTimeMinutes: newPrepTime,
        );
      });

      if (statusChanged && newStatus == 'completed') {
        _pollTimer?.cancel();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Your order is ready! 🎉'),
            duration: Duration(seconds: 4),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } catch (_) {
      // Silently ignore poll errors — will retry next tick
    }
  }

  /// Returns user-friendly time label based on status + stored minutes.
  String _displayTime(String status, int storedMinutes) {
    final s = status.toLowerCase();
    final base = storedMinutes > 0 ? storedMinutes : 15; // fallback if DB hasn't set one yet

    switch (s) {
      case 'confirmed':
      case 'in_kitchen':
        // Full estimated time — kitchen hasn't started yet
        return '$base mins';
      case 'preparing':
        // Roughly 3 mins less than stored (IN_PROGRESS value from kitchen agent)
        final left = (storedMinutes - 3).clamp(1, 99);
        return '$left mins';
      case 'ready':
        // About 1/6 of original time left — almost done
        final left = (base ~/ 6).clamp(1, 99);
        return '$left min${left == 1 ? '' : 's'}';
      case 'completed':
        return '0 mins';
      default:
        return '$base mins';
    }
  }

  double _progressForStatus(String status) {
    final s = status.toLowerCase();
    switch (s) {
      case 'confirmed':
      case 'in_kitchen':
        return 0.15;
      case 'preparing':
        return 0.45;
      case 'ready':
        return 0.75;
      case 'completed':
        return 1.0;
      default:
        return 0.1;
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
                          _displayTime(_order!.status, _order!.estimatedPrepTimeMinutes),
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
                        'confirmed', 'in_kitchen', 'preparing', 'ready', 'completed'
                      ]),
                      inProgress: _isCurrent(_order!.status, ['confirmed']),
                    ),
                    _buildStatusRow(
                      context,
                      icon: Icons.local_fire_department,
                      title: 'Preparing',
                      done: _isDone(_order!.status, [
                        'preparing', 'ready', 'completed'
                      ]),
                      inProgress: _isCurrent(_order!.status, ['in_kitchen', 'preparing']),
                    ),
                    _buildStatusRow(
                      context,
                      icon: Icons.restaurant,
                      title: 'Ready',
                      done: _isDone(_order!.status, ['ready', 'completed']),
                      inProgress: _isCurrent(_order!.status, ['ready']),
                    ),
                    _buildStatusRow(
                      context,
                      icon: Icons.done_all,
                      title: 'Completed',
                      done: _isDone(_order!.status, ['completed']),
                      inProgress: _isCurrent(_order!.status, ['completed']),
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
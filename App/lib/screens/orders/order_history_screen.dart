import 'package:flutter/material.dart';
import 'package:khaadim/app_config.dart';
import 'package:khaadim/models/order.dart';
import 'package:khaadim/screens/dine_in/kiosk_bottom_nav.dart';
import 'package:khaadim/screens/orders/order_tracking_screen.dart';
import 'package:khaadim/services/order_service.dart';
import 'package:khaadim/screens/support/feedback_screen.dart';
import 'package:khaadim/services/favorites_service.dart';

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
    int? customDealId;
    for (final item in order.items) {
      if (item.itemType == 'custom_deal') {
        customDealId = item.itemId;
        break;
      }
    }

    final result = await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => FeedbackScreen(
          orderId: order.orderId,
          feedbackType: customDealId != null ? 'CUSTOM_DEAL' : 'ORDER',
          customDealId: customDealId,
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
                        return _OrderCard(
                          order: order,
                          onFeedback: () => _openFeedback(order),
                          isDelivered: _isDelivered(order.status),
                          statusLabel: _statusLabel(order.status),
                          statusColor: _statusColor(
                              order.status, Theme.of(context).colorScheme),
                          formatDate: _formatDate,
                        );
                      },
                    ),
      bottomNavigationBar: AppConfig.isKiosk
          ? const KioskBottomNav(currentIndex: 3)
          : null,
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Stateful order card — shows heart for custom_deal orders
// ─────────────────────────────────────────────────────────────────────────────
class _OrderCard extends StatefulWidget {
  final Order order;
  final VoidCallback onFeedback;
  final bool isDelivered;
  final String statusLabel;
  final Color statusColor;
  final String Function(DateTime?) formatDate;

  const _OrderCard({
    required this.order,
    required this.onFeedback,
    required this.isDelivered,
    required this.statusLabel,
    required this.statusColor,
    required this.formatDate,
  });

  @override
  State<_OrderCard> createState() => _OrderCardState();
}

class _OrderCardState extends State<_OrderCard> {
  int? _customDealId;
  bool _isFav = false;
  bool _favLoading = false;
  bool _toggling = false;

  @override
  void initState() {
    super.initState();
    for (final item in widget.order.items) {
      if (item.itemType == 'custom_deal') {
        _customDealId = item.itemId;
        break;
      }
    }
    if (_customDealId != null) _loadFavStatus();
  }

  Future<void> _loadFavStatus() async {
    setState(() => _favLoading = true);
    try {
      final res = await FavouritesService.getFavouriteStatus(
        customDealId: _customDealId,
      );
      if (mounted) setState(() => _isFav = res['is_favourite'] == true);
    } catch (_) {}
    if (mounted) setState(() => _favLoading = false);
  }

  Future<void> _toggle() async {
    if (_toggling || _customDealId == null) return;
    setState(() => _toggling = true);
    try {
      final res = await FavouritesService.toggleFavourite(
        customDealId: _customDealId,
      );
      if (!mounted) return;
      final added = res['action'] == 'added';
      setState(() => _isFav = added);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(added
            ? 'Custom deal added to favourites'
            : 'Removed from favourites'),
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 1),
      ));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(e.toString()),
        behavior: SnackBarBehavior.floating,
      ));
    } finally {
      if (mounted) setState(() => _toggling = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = theme.colorScheme;
    final order = widget.order;

    return Card(
      color: theme.cardColor,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      margin: const EdgeInsets.only(bottom: 12),
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => OrderTrackingScreen(orderId: order.orderId),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 12),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Order #${order.orderNumber}',
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: color.onSurface,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Placed on ${widget.formatDate(order.createdAt)}',
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.hintColor),
                    ),
                    const SizedBox(height: 4),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: widget.statusColor.withOpacity(0.15),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                            color: widget.statusColor, width: 1),
                      ),
                      child: Text(
                        widget.statusLabel,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: widget.statusColor,
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
                    style: theme.textTheme.bodyLarge?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: color.primary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  // Heart for custom_deal orders
                  if (_customDealId != null)
                    _favLoading
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : IconButton(
                            icon: Icon(
                              _isFav
                                  ? Icons.favorite
                                  : Icons.favorite_border,
                              color: _isFav ? Colors.redAccent : Colors.grey,
                              size: 20,
                            ),
                            tooltip: _isFav
                                ? 'Remove from favourites'
                                : 'Save to favourites',
                            onPressed: _toggle,
                            padding: EdgeInsets.zero,
                            constraints: const BoxConstraints(),
                          ),
                  const SizedBox(height: 4),
                  if (widget.isDelivered)
                    SizedBox(
                      height: 32,
                      child: OutlinedButton(
                        onPressed: widget.onFeedback,
                        style: OutlinedButton.styleFrom(
                          side: BorderSide(color: color.primary),
                          foregroundColor: color.primary,
                          padding:
                              const EdgeInsets.symmetric(horizontal: 10),
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
  }
}
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:khaadim/utils/app_images.dart';
import 'package:khaadim/screens/navigation/main_screen.dart';
import 'order_tracking_screen.dart';

class OrderConfirmationScreen extends StatelessWidget {
  final int orderId;
  final String orderNumber;
  final double totalAmount;
  final int estimatedPrepTimeMinutes;
  final String? transactionId;

  const OrderConfirmationScreen({
    super.key,
    required this.orderId,
    required this.orderNumber,
    required this.totalAmount,
    required this.estimatedPrepTimeMinutes,
    this.transactionId,
  });

  Widget _buildInfoText(
      String label,
      String value,
      ThemeData theme, {
        bool isHighlight = false,
      }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.hintColor,
            ),
          ),
          Text(
            value,
            style: theme.textTheme.bodyMedium?.copyWith(
              fontWeight: isHighlight ? FontWeight.bold : FontWeight.w500,
              color: isHighlight
                  ? theme.colorScheme.primary
                  : theme.colorScheme.onSurface,
            ),
          ),
        ],
      ),
    );
  }

  String _etaText() {
    if (estimatedPrepTimeMinutes <= 0) {
      return "Preparing soon";
    }
    return "$estimatedPrepTimeMinutes mins";
  }

  String _paymentLabel() {
    return transactionId == null ? "Cash on Delivery" : "Card Payment";
  }

  String _paymentStatusTitle() {
    return transactionId == null ? "Payment Method" : "Payment Successful";
  }

  String _paymentStatusSubtitle() {
    return transactionId == null
        ? "You will pay when the order arrives."
        : "Transaction ID: $transactionId";
  }

  Color _paymentBoxColor() {
    return transactionId == null ? Colors.orange : Colors.green;
  }

  IconData _paymentIcon() {
    return transactionId == null
        ? Icons.local_shipping_outlined
        : Icons.check_circle;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = theme.colorScheme;
    final paymentColor = _paymentBoxColor();

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Image.asset(
                  AppImages.confirm,
                  height: 100,
                  width: 100,
                ),
                const SizedBox(height: 24),
                Text(
                  'Order Confirmed!',
                  style: theme.textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: color.onSurface,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Your order has been successfully placed',
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.hintColor,
                  ),
                ),
                const SizedBox(height: 32),

                Container(
                  padding: const EdgeInsets.symmetric(
                    vertical: 20,
                    horizontal: 16,
                  ),
                  decoration: BoxDecoration(
                    color: theme.cardColor,
                    borderRadius: BorderRadius.circular(12),
                    boxShadow: [
                      if (theme.brightness == Brightness.light)
                        BoxShadow(
                          color: Colors.grey.withOpacity(0.15),
                          blurRadius: 8,
                          offset: const Offset(0, 4),
                        ),
                    ],
                  ),
                  child: Column(
                    children: [
                      _buildInfoText('Order Number', '#$orderNumber', theme),
                      const Divider(),
                      _buildInfoText('Estimated Prep Time', _etaText(), theme),
                      const Divider(),
                      _buildInfoText('Payment Type', _paymentLabel(), theme),
                      const Divider(),
                      _buildInfoText(
                        'Total Amount',
                        'Rs ${totalAmount.toStringAsFixed(2)}',
                        theme,
                        isHighlight: true,
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 24),

                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(
                    vertical: 14,
                    horizontal: 16,
                  ),
                  decoration: BoxDecoration(
                    color: paymentColor.withOpacity(0.08),
                    border: Border.all(color: paymentColor),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        _paymentIcon(),
                        color: paymentColor,
                        size: 20,
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              _paymentStatusTitle(),
                              style: TextStyle(
                                color: paymentColor,
                                fontWeight: FontWeight.bold,
                                fontSize: 13,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              _paymentStatusSubtitle(),
                              style: TextStyle(
                                color: paymentColor.withOpacity(0.9),
                                fontSize: 12,
                                fontFamily:
                                transactionId == null ? null : 'monospace',
                              ),
                            ),
                          ],
                        ),
                      ),
                      if (transactionId != null)
                        IconButton(
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(),
                          icon: Icon(
                            Icons.copy_outlined,
                            color: paymentColor,
                            size: 18,
                          ),
                          onPressed: () {
                            Clipboard.setData(
                              ClipboardData(text: transactionId!),
                            );
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('Transaction ID copied'),
                                duration: Duration(seconds: 2),
                              ),
                            );
                          },
                        ),
                    ],
                  ),
                ),

                const SizedBox(height: 28),

                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: orderId <= 0
                        ? null
                        : () {
                      Navigator.pushReplacement(
                        context,
                        MaterialPageRoute(
                          builder: (_) =>
                              OrderTrackingScreen(orderId: orderId),
                        ),
                      );
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: color.primary,
                      foregroundColor: color.onPrimary,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                    child: const Text('Track Order'),
                  ),
                ),

                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: () {
                      Navigator.pushAndRemoveUntil(
                        context,
                        MaterialPageRoute(
                          builder: (_) => const MainScreen(),
                        ),
                            (route) => false,
                      );
                    },
                    style: OutlinedButton.styleFrom(
                      side: BorderSide(color: color.primary),
                      foregroundColor: color.primary,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                    child: const Text('Back to Home'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: color.primary,
        foregroundColor: color.onPrimary,
        onPressed: () {},
        child: const Icon(Icons.mic_none_rounded),
      ),
    );
  }
}
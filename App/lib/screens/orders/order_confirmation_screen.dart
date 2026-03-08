import 'package:flutter/material.dart';
import 'package:khaadim/utils/app_images.dart';
import 'package:khaadim/screens/navigation/main_screen.dart';
import 'order_tracking_screen.dart';

class OrderConfirmationScreen extends StatelessWidget {
  final int orderId;
  final String orderNumber;
  final double totalAmount;
  final int estimatedPrepTimeMinutes;

  const OrderConfirmationScreen({
    super.key,
    required this.orderId,
    required this.orderNumber,
    required this.totalAmount,
    required this.estimatedPrepTimeMinutes,
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
            style: theme.textTheme.bodyMedium?.copyWith(color: theme.hintColor),
          ),
          Text(
            value,
            style: theme.textTheme.bodyMedium?.copyWith(
              fontWeight: isHighlight ? FontWeight.bold : FontWeight.w500,
              color: isHighlight
                  ? theme.colorScheme.primary
                  : theme.colorScheme.onBackground,
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = theme.colorScheme;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Image.asset(AppImages.confirm, height: 100, width: 100),
                const SizedBox(height: 24),
                Text(
                  'Order Confirmed!',
                  style: theme.textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: color.onBackground,
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
                  padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 16),
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
                      _buildInfoText(
                        'Total Amount',
                        'Rs ${totalAmount.toStringAsFixed(2)}',
                        theme,
                        isHighlight: true,
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 40),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: orderId <= 0
                        ? null
                        : () {
                      Navigator.pushReplacement(
                        context,
                        MaterialPageRoute(
                          builder: (_) => OrderTrackingScreen(orderId: orderId),
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
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: () {
                      Navigator.pushAndRemoveUntil(
                        context,
                        MaterialPageRoute(builder: (_) => const MainScreen()),
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
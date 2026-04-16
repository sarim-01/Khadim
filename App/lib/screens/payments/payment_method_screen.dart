import 'package:flutter/material.dart';
import 'add_payment_screen.dart';
import 'package:khaadim/services/card_service.dart';

class PaymentMethodsScreen extends StatefulWidget {
  const PaymentMethodsScreen({super.key});

  @override
  State<PaymentMethodsScreen> createState() => _PaymentMethodsScreenState();
}

class _PaymentMethodsScreenState extends State<PaymentMethodsScreen> {
  List<Map<String, dynamic>> _cards = [];
  bool _loading = true;

  String _selectedMethod = 'COD';
  int? _selectedCardId;

  @override
  void initState() {
    super.initState();
    _loadCards();
  }

  Future<void> _loadCards() async {
    setState(() => _loading = true);

    try {
      final cards = await CardService.getSavedCards();

      if (!mounted) return;

      setState(() {
        _cards = cards;

        if (_selectedMethod == 'CARD' && _selectedCardId != null) {
          final exists = _cards.any(
                (card) => card['card_id'] == _selectedCardId,
          );

          if (!exists) {
            _selectedMethod = 'COD';
            _selectedCardId = null;
          }
        }
      });
    } catch (e) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to load cards: $e')),
      );
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _deleteCard(int cardId) async {
    try {
      await CardService.deleteCard(cardId: cardId);

      if (!mounted) return;

      if (_selectedCardId == cardId) {
        setState(() {
          _selectedMethod = 'COD';
          _selectedCardId = null;
        });
      }

      await _loadCards();

      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Card deleted successfully')),
      );
    } catch (e) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to delete card: $e')),
      );
    }
  }

  Future<void> _openAddCardScreen() async {
    final result = await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => const AddPaymentScreen(),
      ),
    );

    if (result != null && result is Map) {
      await _loadCards();

      if (!mounted) return;

      setState(() {
        if (result['card_id'] != null) {
          _selectedMethod = 'CARD';
          _selectedCardId = result['card_id'] as int;
        }
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            "Added ${result['card_type']} •••• ${result['last4']}",
          ),
        ),
      );
    }
  }

  void _continueWithSelection() {
    Navigator.pop(context, {
      'payment_method': _selectedMethod,
      'card_id': _selectedMethod == 'CARD' ? _selectedCardId : null,
    });
  }

  Widget _buildMethodTile({
    required String title,
    required String subtitle,
    required bool selected,
    required VoidCallback onTap,
    IconData icon = Icons.payments_outlined,
    Color? iconColor,
    Widget? trailing,
  }) {
    final theme = Theme.of(context);

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 12),
        decoration: BoxDecoration(
          color: theme.colorScheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: selected
                ? theme.colorScheme.primary
                : Colors.grey.withOpacity(0.25),
            width: selected ? 1.5 : 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.05),
              blurRadius: 5,
              offset: const Offset(0, 3),
            ),
          ],
        ),
        child: Row(
          children: [
            Icon(icon, color: iconColor ?? theme.colorScheme.primary),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    style: const TextStyle(
                      color: Colors.grey,
                    ),
                  ),
                ],
              ),
            ),
            trailing ??
                Icon(
                  selected
                      ? Icons.radio_button_checked
                      : Icons.radio_button_off,
                  color: selected
                      ? theme.colorScheme.primary
                      : Colors.grey,
                ),
          ],
        ),
      ),
    );
  }

  Widget _buildCardsList(ThemeData theme) {
    return ListView(
      children: [
        _buildMethodTile(
          title: 'Cash on Delivery',
          subtitle: 'Pay in cash when your order arrives',
          selected: _selectedMethod == 'COD',
          icon: Icons.local_shipping_outlined,
          onTap: () {
            setState(() {
              _selectedMethod = 'COD';
              _selectedCardId = null;
            });
          },
        ),
        if (_cards.isEmpty)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 28, horizontal: 16),
            alignment: Alignment.center,
            child: const Text(
              'No cards added yet',
              style: TextStyle(color: Colors.grey),
            ),
          )
        else
          ..._cards.map((card) {
            final int cardId = card['card_id'] as int;
            final bool selected =
                _selectedMethod == 'CARD' && _selectedCardId == cardId;

            return _buildMethodTile(
              title: "${card['card_type']} •••• ${card['last4']}",
              subtitle: "Expires ${card['expiry']}",
              selected: selected,
              icon: Icons.credit_card,
              onTap: () {
                setState(() {
                  _selectedMethod = 'CARD';
                  _selectedCardId = cardId;
                });
              },
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    selected
                        ? Icons.radio_button_checked
                        : Icons.radio_button_off,
                    color: selected
                        ? theme.colorScheme.primary
                        : Colors.grey,
                  ),
                  const SizedBox(width: 4),
                  IconButton(
                    icon: const Icon(
                      Icons.delete_outline,
                      color: Colors.red,
                    ),
                    onPressed: () => _deleteCard(cardId),
                  ),
                ],
              ),
            );
          }),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SafeArea(
      child: Scaffold(
        appBar: AppBar(
          title: const Text("Payment Methods"),
        ),
        floatingActionButton: FloatingActionButton(
          backgroundColor: theme.colorScheme.primary,
          foregroundColor: Colors.black,
          onPressed: () {},
          child: const Icon(Icons.mic_none_rounded),
        ),
        body: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: theme.colorScheme.primary,
                  foregroundColor: theme.colorScheme.onPrimary,
                  minimumSize: const Size(double.infinity, 48),
                ),
                onPressed: _openAddCardScreen,
                icon: const Icon(Icons.add),
                label: const Text("Add New Card"),
              ),
              const SizedBox(height: 20),
              Expanded(
                child: _loading
                    ? const Center(
                  child: CircularProgressIndicator(),
                )
                    : _buildCardsList(theme),
              ),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: theme.colorScheme.primary,
                    foregroundColor: theme.colorScheme.onPrimary,
                  ),
                  onPressed: _continueWithSelection,
                  child: Text(
                    _selectedMethod == 'COD'
                        ? 'Continue with Cash on Delivery'
                        : 'Continue with Card',
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
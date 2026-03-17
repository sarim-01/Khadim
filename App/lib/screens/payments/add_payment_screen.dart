import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:khaadim/services/card_service.dart';

class AddPaymentScreen extends StatefulWidget {
  const AddPaymentScreen({Key? key}) : super(key: key);

  @override
  State<AddPaymentScreen> createState() => _AddPaymentScreenState();
}

class _AddPaymentScreenState extends State<AddPaymentScreen> {
  final _formKey = GlobalKey<FormState>();
  final _cardNumberController = TextEditingController();
  final _nameController = TextEditingController();
  final _expiryController = TextEditingController();
  final _cvvController = TextEditingController();

  bool _saving = false;

  // ── Luhn algorithm ──────────────────────────────────────────────
  bool _luhn(String number) {
    final digits = number.replaceAll(' ', '');
    if (digits.length < 13 || digits.length > 19) return false;

    int sum = 0;
    bool alternate = false;

    for (int i = digits.length - 1; i >= 0; i--) {
      final int? parsed = int.tryParse(digits[i]);
      if (parsed == null) return false;

      int n = parsed;
      if (alternate) {
        n *= 2;
        if (n > 9) n -= 9;
      }
      sum += n;
      alternate = !alternate;
    }

    return sum % 10 == 0;
  }
  // ── Brand detection ─────────────────────────────────────────────
  String _detectBrand(String number) {
    final d = number.replaceAll(' ', '');
    if (d.startsWith('4')) return 'Visa';
    if (d.startsWith('5')) return 'Mastercard';
    if (d.startsWith('3')) return 'Amex';
    return 'Card';
  }

  IconData _brandIcon(String brand) {
    switch (brand) {
      case 'Visa':
        return Icons.credit_card;
      case 'Mastercard':
        return Icons.credit_card;
      case 'Amex':
        return Icons.credit_card;
      default:
        return Icons.credit_card_outlined;
    }
  }

  Color _brandColor(String brand) {
    switch (brand) {
      case 'Visa':
        return const Color(0xFF1A1F71);
      case 'Mastercard':
        return const Color(0xFFEB001B);
      case 'Amex':
        return const Color(0xFF007BC1);
      default:
        return Colors.grey;
    }
  }

  // ── Expiry validation ───────────────────────────────────────────
  String? _validateExpiry(String? value) {
    if (value == null || value.trim().isEmpty) return 'Enter expiry date';

    final parts = value.split('/');
    if (parts.length != 2) return 'Use MM/YY format';

    final month = int.tryParse(parts[0]);
    final year = int.tryParse(parts[1]);

    if (month == null || year == null) return 'Use MM/YY format';
    if (month < 1 || month > 12) return 'Invalid expiry month';

    final now = DateTime.now();
    final fourDigitYear = 2000 + year;

    final expiryDate = DateTime(fourDigitYear, month + 1, 0);
    final lastMomentOfMonth = DateTime(
      expiryDate.year,
      expiryDate.month,
      expiryDate.day,
      23,
      59,
      59,
    );

    if (lastMomentOfMonth.isBefore(now)) {
      return 'Card is expired';
    }

    return null;
  }
  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;

    final raw = _cardNumberController.text.replaceAll(' ', '');
    final last4 = raw.substring(raw.length - 4);
    final brand = _detectBrand(raw);
    final expiry = _expiryController.text.trim();
    final name = _nameController.text.trim();

    setState(() => _saving = true);
    try {
      final res = await CardService.addCard(
        cardType: brand,
        last4: last4,
        cardholderName: name,
        expiry: expiry,
      );
      if (!mounted) return;
      Navigator.pop(context, {
        'card_id': res['card_id'],
        'card_type': brand,
        'last4': last4,
        'cardholder_name': name,
        'expiry': expiry,
        'is_default': false,
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to save card: $e')),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  void dispose() {
    _cardNumberController.dispose();
    _nameController.dispose();
    _expiryController.dispose();
    _cvvController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final brand = _detectBrand(_cardNumberController.text);
    final rawNum = _cardNumberController.text.replaceAll(' ', '');
    final masked = rawNum.isEmpty
        ? '•••• •••• •••• ••••'
        : rawNum.padRight(16, '•').replaceAllMapped(
            RegExp(r'.{4}'), (m) => '${m.group(0)} ').trim();
    final displayName = _nameController.text.isEmpty
        ? 'CARDHOLDER NAME'
        : _nameController.text.toUpperCase();
    final displayExpiry =
        _expiryController.text.isEmpty ? 'MM/YY' : _expiryController.text;

    return SafeArea(
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Add Payment Method'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back),
            onPressed: () => Navigator.pop(context),
          ),
        ),
        floatingActionButton: FloatingActionButton(
          backgroundColor: theme.colorScheme.primary,
          foregroundColor: Colors.black,
          onPressed: () {},
          child: const Icon(Icons.mic_none_rounded),
        ),
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              // ── Card Preview ──────────────────────────────────
              AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                width: double.infinity,
                height: 190,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      _brandColor(brand).withOpacity(0.85),
                      Colors.black87,
                    ],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: [
                    BoxShadow(
                      color: _brandColor(brand).withOpacity(0.4),
                      blurRadius: 16,
                      offset: const Offset(0, 8),
                    ),
                  ],
                ),
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            brand,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 18,
                              fontWeight: FontWeight.bold,
                              letterSpacing: 2,
                            ),
                          ),
                          Icon(_brandIcon(brand),
                              color: Colors.white70, size: 32),
                        ],
                      ),
                      const Spacer(),
                      Text(
                        masked,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 20,
                          letterSpacing: 3,
                          fontFamily: 'monospace',
                        ),
                      ),
                      const SizedBox(height: 16),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('CARD HOLDER',
                                  style: TextStyle(
                                      color: Colors.white60, fontSize: 10)),
                              Text(displayName,
                                  style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 13,
                                      fontWeight: FontWeight.w600)),
                            ],
                          ),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              const Text('EXPIRES',
                                  style: TextStyle(
                                      color: Colors.white60, fontSize: 10)),
                              Text(displayExpiry,
                                  style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 13,
                                      fontWeight: FontWeight.w600)),
                            ],
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 24),

              // ── Form ─────────────────────────────────────────
              Form(
                key: _formKey,
                child: Column(
                  children: [
                    // Card Number
                    TextFormField(
                      controller: _cardNumberController,
                      decoration: InputDecoration(
                        labelText: 'Card Number',
                        hintText: '1234 5678 9012 3456',
                        border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(10)),
                        filled: true,
                      ),
                      keyboardType: TextInputType.number,
                      inputFormatters: [
                        FilteringTextInputFormatter.digitsOnly,
                        _CardNumberFormatter(),
                      ],
                      maxLength: 19,
                      onChanged: (_) => setState(() {}),
                      validator: (v) {
                        final digits = (v ?? '').replaceAll(' ', '').trim();

                        if (digits.isEmpty) {
                          return 'Enter card number';
                        }

                        if (!RegExp(r'^[0-9]+$').hasMatch(digits)) {
                          return 'Card number must contain digits only';
                        }

                        if (digits.length < 13 || digits.length > 19) {
                          return 'Card number must be 13 to 19 digits';
                        }

                        if (!_luhn(digits)) {
                          return 'Invalid card number';
                        }

                        return null;
                      },
                    ),
                    const SizedBox(height: 16),

                    // Cardholder Name
                    TextFormField(
                      controller: _nameController,
                      decoration: InputDecoration(
                        labelText: 'Cardholder Name',
                        border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(10)),
                        filled: true,
                      ),
                      textCapitalization: TextCapitalization.words,
                      onChanged: (_) => setState(() {}),
                      validator: (v) {
                        if (v == null || v.trim().length < 3) {
                          return 'Enter a valid name (min 3 characters)';
                        }
                        if (!RegExp(r"^[a-zA-Z ]+$").hasMatch(v.trim())) {
                          return 'Name must contain letters and spaces only';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),

                    // Expiry + CVV
                    Row(
                      children: [
                        Expanded(
                          child: TextFormField(
                            controller: _expiryController,
                            decoration: InputDecoration(
                              labelText: 'Expiry Date',
                              hintText: 'MM/YY',
                              border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(10)),
                              filled: true,
                            ),
                            keyboardType: TextInputType.number,
                            inputFormatters: [
                              FilteringTextInputFormatter.digitsOnly,
                              _ExpiryFormatter(),
                            ],
                            maxLength: 5,
                            onChanged: (_) => setState(() {}),
                            validator: _validateExpiry,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: TextFormField(
                            controller: _cvvController,
                            decoration: InputDecoration(
                              labelText: 'CVV',
                              hintText: '123',
                              border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(10)),
                              filled: true,
                            ),
                            keyboardType: TextInputType.number,
                            inputFormatters: [
                              FilteringTextInputFormatter.digitsOnly,
                            ],
                            maxLength: 3,
                            obscureText: true,
                            validator: (v) {
                              final brand = _detectBrand(_cardNumberController.text);
                              final requiredLength = brand == 'Amex' ? 4 : 3;

                              if (v == null || v.trim().isEmpty) {
                                return 'Enter CVV';
                              }

                              if (v.length != requiredLength) {
                                return 'CVV must be $requiredLength digits';
                              }

                              return null;
                            },
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 24),

                    // Add Card Button
                    SizedBox(
                      width: double.infinity,
                      height: 50,
                      child: ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: theme.colorScheme.primary,
                          foregroundColor: theme.colorScheme.onPrimary,
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10)),
                        ),
                        onPressed: _saving ? null : _submit,
                        child: _saving
                            ? const SizedBox(
                                height: 22,
                                width: 22,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2, color: Colors.white),
                              )
                            : const Text('Add Card',
                                style: TextStyle(fontSize: 16)),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── Input Formatters ───────────────────────────────────────────────

class _CardNumberFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
      TextEditingValue oldValue, TextEditingValue newValue) {
    final digits = newValue.text.replaceAll(' ', '');
    final buffer = StringBuffer();
    for (int i = 0; i < digits.length; i++) {
      if (i > 0 && i % 4 == 0) buffer.write(' ');
      buffer.write(digits[i]);
    }
    final str = buffer.toString();
    return newValue.copyWith(
      text: str,
      selection: TextSelection.collapsed(offset: str.length),
    );
  }
}

class _ExpiryFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
      TextEditingValue oldValue, TextEditingValue newValue) {
    final digits = newValue.text.replaceAll('/', '');
    if (digits.length >= 3) {
      final str = '${digits.substring(0, 2)}/${digits.substring(2)}';
      return newValue.copyWith(
        text: str,
        selection: TextSelection.collapsed(offset: str.length),
      );
    }
    return newValue;
  }
}


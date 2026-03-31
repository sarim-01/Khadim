import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:khaadim/providers/dine_in_provider.dart';
import 'package:khaadim/services/dine_in_service.dart';
import 'package:provider/provider.dart';

class TablePinScreen extends StatefulWidget {
  const TablePinScreen({super.key});

  @override
  State<TablePinScreen> createState() => _TablePinScreenState();
}

class _TablePinScreenState extends State<TablePinScreen> {
  final _formKey = GlobalKey<FormState>();
  final TextEditingController _tableNumberController = TextEditingController();
  final TextEditingController _pinController = TextEditingController();

  final DineInService _dineInService = DineInService();

  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final existingSession = context.read<DineInProvider>().sessionId;
      if (existingSession != null && existingSession.isNotEmpty) {
        Navigator.pushReplacementNamed(context, '/kiosk-home');
      }
    });
  }

  @override
  void dispose() {
    _tableNumberController.dispose();
    _pinController.dispose();
    super.dispose();
  }

  Future<void> _startOrdering() async {
    if (!_formKey.currentState!.validate()) return;

    final tableNumber = _tableNumberController.text.trim();
    final pin = _pinController.text.trim();

    setState(() => _isLoading = true);

    try {
      final result = await _dineInService.tableLogin(tableNumber, pin);

      final sessionId = (result['session_id'] ?? '').toString();
      final tableId = (result['table_id'] ?? '').toString();
      final resolvedTableNumber =
          (result['table_number'] ?? tableNumber).toString();
        final token = (result['token'] ?? result['access_token'] ?? '').toString();

      if (sessionId.isEmpty) {
        throw Exception('Table login succeeded but session_id is missing.');
      }
      if (tableId.isEmpty) {
        throw Exception('Table login succeeded but table_id is missing.');
      }

      if (!mounted) return;

      context.read<DineInProvider>().startSession(
        sessionId,
        tableId,
        resolvedTableNumber,
        token: token.isEmpty ? null : token,
      );

      Navigator.pushReplacementNamed(context, '/kiosk-home');
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString())),
      );
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: Container(
        width: double.infinity,
        height: double.infinity,
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Color(0xFF010917),
              Color(0xFF021433),
            ],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 430),
                child: Card(
                  color: theme.colorScheme.surface.withValues(alpha: 0.94),
                  elevation: 14,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(20),
                    side: BorderSide(
                      color: theme.colorScheme.primary.withValues(alpha: 0.35),
                      width: 1,
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 22,
                      vertical: 26,
                    ),
                    child: Form(
                      key: _formKey,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Center(
                            child: Image.asset(
                              'assets/images/khaadim_logo_dark.png',
                              width: 92,
                              height: 92,
                              errorBuilder: (context, error, stackTrace) {
                                return Text(
                                  'Khadim',
                                  style: theme.textTheme.headlineLarge?.copyWith(
                                    color: theme.colorScheme.primary,
                                  ),
                                );
                              },
                            ),
                          ),
                          const SizedBox(height: 14),
                          Text(
                            'Welcome! Enter your table details',
                            textAlign: TextAlign.center,
                            style: theme.textTheme.bodyLarge,
                          ),
                          const SizedBox(height: 24),
                          TextFormField(
                            controller: _tableNumberController,
                            textCapitalization: TextCapitalization.characters,
                            decoration: const InputDecoration(
                              labelText: 'Table Number',
                              hintText: 'T01',
                              prefixIcon: Icon(Icons.table_restaurant_outlined),
                            ),
                            validator: (value) {
                              if (value == null || value.trim().isEmpty) {
                                return 'Please enter your table number';
                              }
                              return null;
                            },
                          ),
                          const SizedBox(height: 16),
                          TextFormField(
                            controller: _pinController,
                            obscureText: true,
                            keyboardType: TextInputType.number,
                            inputFormatters: [
                              FilteringTextInputFormatter.digitsOnly,
                              LengthLimitingTextInputFormatter(6),
                            ],
                            decoration: const InputDecoration(
                              labelText: 'PIN',
                              hintText: '6-digit PIN',
                              prefixIcon: Icon(Icons.lock_outline),
                            ),
                            validator: (value) {
                              final pin = value?.trim() ?? '';
                              if (pin.isEmpty) {
                                return 'Please enter your PIN';
                              }
                              if (pin.length != 6) {
                                return 'PIN must be 6 digits';
                              }
                              return null;
                            },
                          ),
                          const SizedBox(height: 28),
                          SizedBox(
                            height: 54,
                            child: ElevatedButton(
                              onPressed: _isLoading ? null : _startOrdering,
                              child: _isLoading
                                  ? const SizedBox(
                                      width: 22,
                                      height: 22,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2.4,
                                      ),
                                    )
                                  : const Text('Start Ordering'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

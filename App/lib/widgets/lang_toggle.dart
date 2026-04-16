import 'package:flutter/material.dart';

/// LangToggle — EN / UR pill toggle for chat header.
/// Uses app theme primary (gold) for active pill.
///
/// Usage:
///   LangToggle(
///     isUrdu:   _isUrdu,
///     onToggle: _toggleLanguage,
///   )
class LangToggle extends StatelessWidget {
  /// true = Urdu selected, false = English selected
  final bool         isUrdu;
  final VoidCallback onToggle;

  const LangToggle({
    super.key,
    required this.isUrdu,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary; // gold

    return GestureDetector(
      onTap: onToggle,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 3),
        decoration: BoxDecoration(
          color:        color.withOpacity(0.08),
          borderRadius: BorderRadius.circular(20),
          border:       Border.all(color: color.withOpacity(0.35), width: 1),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _Pill(label: 'EN', active: !isUrdu, color: color),
            const SizedBox(width: 2),
            _Pill(label: 'UR', active: isUrdu,  color: color),
          ],
        ),
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  final String label;
  final bool   active;
  final Color  color;

  const _Pill({
    required this.label,
    required this.active,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color:        active ? color : Colors.transparent,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontFamily: 'Poppins',
          fontSize:   12,
          fontWeight: FontWeight.w700,
          color:      active ? Colors.black : color,
        ),
      ),
    );
  }
}
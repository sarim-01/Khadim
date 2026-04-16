import 'package:flutter/material.dart';

/// CircleIconButton — reusable gold circle action button.
/// Used in chat (send), and can be reused anywhere in the app.
///
/// Usage:
///   CircleIconButton(
///     icon:  Icons.send_rounded,
///     onTap: _sendMessage,
///   )
///
///   // Custom color override:
///   CircleIconButton(
///     icon:  Icons.close,
///     color: Colors.redAccent,
///     onTap: _cancel,
///   )
class CircleIconButton extends StatelessWidget {
  final IconData      icon;
  final VoidCallback? onTap;
  final Color?        color;       // defaults to theme primary (gold)
  final Color?        iconColor;   // defaults to black (on gold)
  final double        size;

  const CircleIconButton({
    super.key,
    required this.icon,
    required this.onTap,
    this.color,
    this.iconColor,
    this.size = 46,
  });

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    final bg      = color ?? primary;
    final fg      = iconColor ?? Colors.black;

    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: size, height: size,
        decoration: BoxDecoration(
          color: bg,
          shape: BoxShape.circle,
          boxShadow: [
            BoxShadow(
              color:      bg.withOpacity(0.32),
              blurRadius: 8,
              offset:     const Offset(0, 3),
            ),
          ],
        ),
        child: Icon(icon, color: fg, size: size * 0.45),
      ),
    );
  }
}
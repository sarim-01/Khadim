import 'package:flutter/material.dart';

/// ChatBubble — reusable message bubble for chat screen.
/// Automatically detects Urdu (RTL) text and adjusts direction.
/// Uses app theme primary (gold) for user bubbles.
class ChatBubble extends StatelessWidget {
  final String text;
  final bool   isUser;
  final bool   isLoading; // shows TypingIndicator instead of text

  const ChatBubble({
    super.key,
    required this.text,
    required this.isUser,
    this.isLoading = false,
  });

  /// Detect if text contains Urdu/Arabic characters → RTL
  static bool _isUrdu(String text) =>
      RegExp(r'[\u0600-\u06FF]').hasMatch(text);

  @override
  Widget build(BuildContext context) {
    final theme  = Theme.of(context);
    final isUrdu = _isUrdu(text);

    // Colors
    final bgColor   = isUser
        ? theme.colorScheme.primary          // gold
        : theme.colorScheme.surface;         // dark surface / white
    final textColor = isUser
        ? Colors.black                        // black on gold
        : theme.colorScheme.onSurface;       // white/dark on surface

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.76,
        ),
        margin: EdgeInsets.only(
          top: 4, bottom: 4,
          left:  isUser ? 52 : 8,
          right: isUser ? 8  : 52,
        ),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: bgColor,
          borderRadius: BorderRadius.only(
            topLeft:     const Radius.circular(16),
            topRight:    const Radius.circular(16),
            bottomLeft:  Radius.circular(isUser ? 16 : 4),
            bottomRight: Radius.circular(isUser ? 4  : 16),
          ),
          boxShadow: [
            BoxShadow(
              color:      Colors.black.withOpacity(0.12),
              blurRadius: 6,
              offset:     const Offset(0, 2),
            ),
          ],
        ),
        child: isLoading
            ? const _LoadingDots() // inline — driven by TypingIndicator
            : Text(
          text,
          textDirection: isUrdu
              ? TextDirection.rtl
              : TextDirection.ltr,
          style: TextStyle(
            fontFamily: 'Poppins',
            fontSize:   14.5,
            height:     1.5,
            color:      textColor,
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// Internal animated dots — used only inside ChatBubble
// For standalone use, import TypingIndicator widget instead
// ─────────────────────────────────────────────────────────────
class _LoadingDots extends StatefulWidget {
  const _LoadingDots();

  @override
  State<_LoadingDots> createState() => _LoadingDotsState();
}

class _LoadingDotsState extends State<_LoadingDots>
    with TickerProviderStateMixin {
  late final List<AnimationController> _ctrls;
  late final List<Animation<double>>   _anims;

  @override
  void initState() {
    super.initState();
    _ctrls = List.generate(3, (_) => AnimationController(
      vsync:    this,
      duration: const Duration(milliseconds: 480),
    ));
    _anims = List.generate(3, (i) {
      Future.delayed(Duration(milliseconds: i * 140), () {
        if (mounted) _ctrls[i].repeat(reverse: true);
      });
      return Tween<double>(begin: 0, end: -5).animate(
        CurvedAnimation(parent: _ctrls[i], curve: Curves.easeInOut),
      );
    });
  }

  @override
  void dispose() {
    for (final c in _ctrls) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return SizedBox(
      height: 20,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: List.generate(3, (i) => AnimatedBuilder(
          animation: _anims[i],
          builder: (_, __) => Transform.translate(
            offset: Offset(0, _anims[i].value),
            child: Container(
              width:  7,
              height: 7,
              margin: const EdgeInsets.symmetric(horizontal: 2.5),
              decoration: BoxDecoration(
                color: color.withOpacity(0.7),
                shape: BoxShape.circle,
              ),
            ),
          ),
        )),
      ),
    );
  }
}
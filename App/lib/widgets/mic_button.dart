import 'package:flutter/material.dart';

/// MicButton — hold-to-record mic button with pulse animation.
/// Uses app theme primary (gold) normally, red when recording.
///
/// Usage:
///   MicButton(
///     isRecording: _isRecording,
///     onPressDown: _onMicDown,
///     onPressUp:   _onMicUp,
///     onCancel:    _onMicCancel,
///   )
class MicButton extends StatefulWidget {
  final bool isRecording;
  final bool isProcessing;
  final VoidCallback onPressDown;
  final VoidCallback onPressUp;
  final VoidCallback onCancel;

  const MicButton({
    super.key,
    required this.isRecording,
    this.isProcessing = false,
    required this.onPressDown,
    required this.onPressUp,
    required this.onCancel,
  });

  @override
  State<MicButton> createState() => _MicButtonState();
}

class _MicButtonState extends State<MicButton>
    with SingleTickerProviderStateMixin {
  late AnimationController _anim;
  late Animation<double> _pulse;

  @override
  void initState() {
    super.initState();
    _anim = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _pulse = Tween<double>(begin: 1.0, end: 1.22).animate(
      CurvedAnimation(parent: _anim, curve: Curves.easeInOut),
    );
  }

  @override
  void didUpdateWidget(MicButton old) {
    super.didUpdateWidget(old);
    if (widget.isRecording && !old.isRecording) {
      _anim.repeat(reverse: true);
    } else if (!widget.isRecording && old.isRecording) {
      _anim.stop();
      _anim.reset();
    }
  }

  @override
  void dispose() {
    _anim.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary; // gold
    final color = widget.isProcessing
        ? Colors.blueGrey
        : (widget.isRecording ? Colors.redAccent : primary);

    return IgnorePointer(
      ignoring: widget.isProcessing,
      child: GestureDetector(
        onLongPressStart: (_) => widget.onPressDown(),
        onLongPressEnd: (_) => widget.onPressUp(),
        onLongPressCancel: () => widget.onCancel(),
        child: AnimatedBuilder(
          animation: _anim,
          builder: (_, child) => Transform.scale(
            scale: widget.isRecording ? _pulse.value : 1.0,
            child: child,
          ),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            width: 46,
            height: 46,
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: color.withOpacity(0.35),
                  blurRadius: 10,
                  offset: const Offset(0, 3),
                ),
              ],
            ),
            child: widget.isProcessing
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                    ),
                  )
                : Icon(
                    widget.isRecording ? Icons.stop_rounded : Icons.mic,
                    color: widget.isRecording ? Colors.white : Colors.black,
                    size: 21,
                  ),
          ),
        ),
      ),
    );
  }
}

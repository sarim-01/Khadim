import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';

/// Voice confirmation dialog with Yes/No buttons and TTS playback.
///
/// Pass [sharedTts] (from VoiceOrderHandler.tts) so the dialog reuses
/// the same TTS engine — prevents two engines talking over each other.
class VoiceConfirmationDialog extends StatefulWidget {
  final String message;
  final String? messageUrdu;
  final VoidCallback onConfirm;
  final VoidCallback onCancel;
  final bool isUrdu;

  /// Shared TTS instance from VoiceOrderHandler. If null, a local one is created.
  final FlutterTts? sharedTts;

  const VoiceConfirmationDialog({
    super.key,
    required this.message,
    this.messageUrdu,
    required this.onConfirm,
    required this.onCancel,
    this.isUrdu = true,
    this.sharedTts,
  });

  @override
  State<VoiceConfirmationDialog> createState() =>
      _VoiceConfirmationDialogState();
}

class _VoiceConfirmationDialogState extends State<VoiceConfirmationDialog> {
  late final FlutterTts _tts;
  late final bool _ownsInstance; // true = we created it, so we must close it
  bool _ttsReady = false;

  @override
  void initState() {
    super.initState();
    if (widget.sharedTts != null) {
      _tts = widget.sharedTts!;
      _ownsInstance = false;
    } else {
      _tts = FlutterTts();
      _ownsInstance = true;
    }
    _initTTS();
  }

  Future<void> _initTTS() async {
    try {
      // Only configure if we own the instance —
      // shared instance is already configured by VoiceOrderHandler
      if (_ownsInstance) {
        await _tts.setLanguage(widget.isUrdu ? 'ur-PK' : 'en-US');
        await _tts.setSpeechRate(0.5);
        await _tts.setVolume(1.0);
        await _tts.setPitch(1.0);
      }
      setState(() => _ttsReady = true);

      // Auto-play message
      await _speak(
        widget.isUrdu && widget.messageUrdu != null
            ? widget.messageUrdu!
            : widget.message,
      );
    } catch (e) {
      debugPrint('[VoiceConfirmation] TTS init error: $e');
    }
  }

  Future<void> _speak(String text) async {
    if (!_ttsReady || text.isEmpty) return;
    try {
      await _tts.stop();
      await _tts.speak(text);
    } catch (e) {
      debugPrint('[VoiceConfirmation] Speak error: $e');
    }
  }

  @override
  void dispose() {
    _tts.stop();
    // Only close if we created our own instance
    if (_ownsInstance) {
      _tts.stop();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final displayMessage = widget.isUrdu && widget.messageUrdu != null
        ? widget.messageUrdu!
        : widget.message;

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Icon
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.orange.shade50,
                shape: BoxShape.circle,
              ),
              child: Icon(Icons.mic, size: 40, color: Colors.orange.shade700),
            ),

            const SizedBox(height: 16),

            // Message
            Text(
              displayMessage,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w500),
            ),

            const SizedBox(height: 24),

            // Buttons
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                // Cancel
                Expanded(
                  child: OutlinedButton(
                    onPressed: () {
                      _tts.stop();
                      widget.onCancel();
                      Navigator.of(context).pop();
                    },
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      side: BorderSide(color: Colors.grey.shade400),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: Text(
                      widget.isUrdu ? 'نہیں' : 'No',
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                  ),
                ),

                const SizedBox(width: 12),

                // Confirm
                Expanded(
                  child: ElevatedButton(
                    onPressed: () {
                      _tts.stop();
                      widget.onConfirm();
                      Navigator.of(context).pop();
                    },
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      backgroundColor: Colors.orange.shade600,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: Text(
                      widget.isUrdu ? 'ہاں' : 'Yes',
                      style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                          color: Colors.white),
                    ),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 12),

            Text(
              widget.isUrdu
                  ? 'یا "ہاں" یا "نہیں" بولیں'
                  : 'Or say "yes" or "no"',
              style: TextStyle(
                fontSize: 12,
                color: Colors.grey.shade600,
                fontStyle: FontStyle.italic,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Show the voice confirmation dialog.
///
/// Pass [sharedTts] from your VoiceOrderHandler to prevent TTS overlap:
/// ```dart
/// showVoiceConfirmation(
///   context:   context,
///   message:   'Confirm order?',
///   sharedTts: voiceOrderHandler.tts,
/// );
/// ```
Future<bool?> showVoiceConfirmation({
  required BuildContext context,
  required String message,
  String? messageUrdu,
  bool isUrdu = true,
  FlutterTts? sharedTts,
}) {
  return showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (context) => VoiceConfirmationDialog(
      message: message,
      messageUrdu: messageUrdu,
      isUrdu: isUrdu,
      sharedTts: sharedTts,
      onConfirm: () => Navigator.of(context).pop(true),
      onCancel: () => Navigator.of(context).pop(false),
    ),
  );
}

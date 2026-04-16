import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_sound/flutter_sound.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:path_provider/path_provider.dart';
import 'package:khaadim/services/chat_service.dart';
import 'package:flutter_tts/flutter_tts.dart';

class ChatBottomSheet extends StatefulWidget {
  final String mode;
  final ScrollController scrollController;

  const ChatBottomSheet({
    super.key,
    required this.mode,
    required this.scrollController,
  });

  @override
  State<ChatBottomSheet> createState() => _ChatBottomSheetState();
}

class _ChatBottomSheetState extends State<ChatBottomSheet>
    with SingleTickerProviderStateMixin {
  final FlutterSoundRecorder _recorder = FlutterSoundRecorder();
  final ChatService _chatService = ChatService();
  final FlutterTts tts = FlutterTts();

  final List<Map<String, dynamic>> _messages = [];

  bool _isRecording = false;
  bool _isSending = false;
  late String _sessionId;

  late AnimationController _micController;
  late Animation<double> _micAnimation;

  @override
  void initState() {
    super.initState();
    _sessionId = DateTime.now().millisecondsSinceEpoch.toString();

    _initTTS();

    _micController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 1),
    )..repeat(reverse: true);

    _micAnimation = Tween<double>(begin: 1.0, end: 1.3).animate(
      CurvedAnimation(
        parent: _micController,
        curve: Curves.easeInOut,
      ),
    );
  }

  @override
  void dispose() {
    _micController.dispose();
    _recorder.closeRecorder();
    super.dispose();
  }

  // -------------------------------------------------------------
  // INITIALIZE TTS (English)
  // -------------------------------------------------------------
  Future<void> _initTTS() async {
    await tts.setLanguage("en-US");
    await tts.setPitch(1.0);
    await tts.setSpeechRate(0.5);
    await tts.setVolume(1.0);
  }

  // -------------------------------------------------------------
  // START RECORDING
  // -------------------------------------------------------------
  Future<void> _startRecording() async {
    if (_isRecording) return;

    final mic = await Permission.microphone.request();
    if (!mic.isGranted) return;

    await _recorder.openRecorder();

    final dir = await getTemporaryDirectory();
    final filePath =
        '${dir.path}/chat_${DateTime.now().millisecondsSinceEpoch}.aac';

    await _recorder.startRecorder(
      toFile: filePath,
      codec: Codec.aacADTS,
      sampleRate: 16000,
    );

    setState(() => _isRecording = true);
  }

  // -------------------------------------------------------------
  // STOP RECORDING
  // -------------------------------------------------------------
  Future<void> _stopRecording() async {
    if (!_isRecording) return;

    final path = await _recorder.stopRecorder();
    setState(() => _isRecording = false);

    if (path == null) return;

    File audioFile = File(path);
    _sendVoice(audioFile);
  }

  // -------------------------------------------------------------
  // SEND VOICE MESSAGE
  // -------------------------------------------------------------
  Future<void> _sendVoice(File file) async {
    if (_isSending) return;

    setState(() {
      _isSending = true;
      _messages.add({"sender": "user", "text": "Processing voice..."});
    });

    _scrollToBottom();

    try {
      final result = await _chatService.sendVoiceMessage(
        _sessionId,
        file,
        "voice",
        "en",
      );

      final transcript = result["transcript"] ?? "";
      final reply = result["reply"] ?? "";

      setState(() {
        _messages.removeLast();
        if (transcript.toString().trim().isNotEmpty) {
          _messages.add({"sender": "user", "text": transcript});
        }
        _messages.add({
          "sender": "ai",
          "text": reply.toString().trim().isEmpty
              ? "I could not understand that."
              : reply
        });
      });

      _scrollToBottom();
      await tts.speak(reply.toString());
    } catch (e) {
      setState(() {
        _messages.removeLast();
        _messages.add({
          "sender": "ai",
          "text": "Voice request failed. Please try again."
        });
      });
      _scrollToBottom();
    } finally {
      if (mounted) {
        setState(() => _isSending = false);
      }
    }
  }

  // -------------------------------------------------------------
  // SCROLL TO BOTTOM
  // -------------------------------------------------------------
  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.scrollController.hasClients) {
        widget.scrollController.animateTo(
          widget.scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  // -------------------------------------------------------------
  // UI
  // -------------------------------------------------------------
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Container(
              width: 60,
              height: 5,
              margin: const EdgeInsets.only(bottom: 16),
              decoration: BoxDecoration(
                color: Colors.black26,
                borderRadius: BorderRadius.circular(10),
              ),
            ),

            // ---------------- Messages ----------------
            Expanded(
              child: ListView.builder(
                controller: widget.scrollController,
                itemCount: _messages.length,
                itemBuilder: (_, i) {
                  final msg = _messages[i];
                  final isUser = msg["sender"] == "user";

                  return Align(
                    alignment:
                        isUser ? Alignment.centerRight : Alignment.centerLeft,
                    child: Container(
                      margin: const EdgeInsets.symmetric(vertical: 6),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 12),
                      decoration: BoxDecoration(
                        color: isUser ? Colors.deepOrange : Colors.white,
                        borderRadius: BorderRadius.circular(16),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.05),
                            blurRadius: 6,
                            offset: const Offset(0, 2),
                          )
                        ],
                      ),
                      child: Text(
                        msg["text"],
                        style: TextStyle(
                          fontSize: 15,
                          color: isUser ? Colors.white : Colors.black87,
                          height: 1.4,
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),

            const SizedBox(height: 12),
            Text(
              _isSending
                  ? 'Sending...'
                  : _isRecording
                      ? 'Recording... tap stop when done'
                      : 'Tap mic to speak',
              style: theme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 10),

            // ---------------- Record Button ----------------
            _isRecording
                ? ElevatedButton.icon(
                    onPressed: _isSending ? null : _stopRecording,
                    icon: const Icon(Icons.stop),
                    label: const Text("Stop Recording"),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.redAccent,
                      foregroundColor: Colors.white,
                    ),
                  )
                : ScaleTransition(
                    scale: _micAnimation,
                    child: ElevatedButton.icon(
                      onPressed: _isSending ? null : _startRecording,
                      icon: const Icon(Icons.mic),
                      label: const Text("Speak"),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: theme.colorScheme.primary,
                        foregroundColor: Colors.black,
                      ),
                    ),
                  ),
          ],
        ),
      ),
    );
  }
}

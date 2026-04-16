import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';

class TestUrduTTSPage extends StatefulWidget {
  const TestUrduTTSPage({super.key});

  @override
  State<TestUrduTTSPage> createState() => _TestUrduTTSPageState();
}

class _TestUrduTTSPageState extends State<TestUrduTTSPage> {
  final FlutterTts tts = FlutterTts();
  String _status = "Press the button to test Urdu TTS";

  @override
  void initState() {
    super.initState();
    _configureTTS();
    _setupDebugHandlers();
  }

  /// ------------------------
  /// DEBUG LISTENERS
  /// ------------------------
  void _setupDebugHandlers() {
    tts.setStartHandler(() {
      print("TTS DEBUG: Speech started");
    });

    tts.setCompletionHandler(() {
      print("TTS DEBUG: Speech completed");
    });

    tts.setCancelHandler(() {
      print("TTS DEBUG: Speech canceled");
    });

    tts.setErrorHandler((msg) {
      print("TTS ERROR: $msg");
    });
  }

  /// ------------------------
  /// INITIAL CONFIG
  /// ------------------------
  Future<void> _configureTTS() async {
    print("TTS DEBUG: Configuring TTS");

    await tts.setSpeechRate(0.5);
    await tts.setPitch(1.0);
    await tts.setVolume(1.0);

    var voices = await tts.getVoices;
    print("TTS DEBUG: Available voices → $voices");

    /// Try to detect Urdu voice
    var urduVoice = voices.firstWhere(
          (v) =>
      (v["locale"]?.toString().toLowerCase().contains("ur") ?? false),
      orElse: () => null,
    );

    if (urduVoice == null) {
      print("TTS ERROR: No Urdu voice found");
      setState(() {
        _status = "⚠ No Urdu voice installed on device. Install Google Text-to-Speech.";
      });
      return;
    }

    print("TTS DEBUG: Urdu voice found → $urduVoice");

    await tts.setVoice({
      "name": urduVoice["name"],
      "locale": urduVoice["locale"],
    });

    setState(() {
      _status = "Using Urdu voice: ${urduVoice["name"]}";
    });
  }

  /// ------------------------
  /// SPEAK BUTTON
  /// ------------------------
  Future<void> _speak() async {
    print("TTS DEBUG: Speak button pressed");

    await tts.setLanguage("ur-PK");

    /// LONG URDU TEST SENTENCE
    const longText = """
    السلام علیکم! یہ ایک طویل ٹیسٹ پیغام ہے تاکہ ہم یہ دیکھ سکیں کہ 
    ٹیکسٹ ٹو اسپیچ اردو زبان میں کتنی روانی کے ساتھ جملے پڑھتا ہے۔ 
    اگر آواز واضح، قدرتی اور سمجھ میں آنے والی ہو تو اس کا مطلب ہے 
    کہ آپ کے موبائل میں اردو کی مکمل سپورٹ موجود ہے۔ 
    براہِ کرم غور سے سنیں اور بتائیں کہ آواز کی کوالٹی کیسی لگی۔
    """;

    var result = await tts.speak(longText);
    print("TTS DEBUG: speak() returned → $result");
  }

  /// ------------------------
  /// UI
  /// ------------------------
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Test Urdu TTS")),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            Text(_status, style: const TextStyle(fontSize: 16)),
            const SizedBox(height: 30),
            ElevatedButton(
              onPressed: _speak,
              child: const Text("Speak Urdu"),
            )
          ],
        ),
      ),
    );
  }
}

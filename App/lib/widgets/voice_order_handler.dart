// lib/widgets/voice_order_handler.dart
// REPLACE existing file entirely.
//
// Key changes from original:
//   1. ConversationMemory added — stores last 10 turns
//   2. Every API call passes conversationHistory from memory
//   3. After each transcript, memory.add(user) before executing
//   4. After each reply, memory.add(assistant)
//   5. "Yes/ہاں" detection: if last turn was a deal offer and
//      user says yes → run custom deal flow with stored query
//   6. _pendingCustomDealQuery stores the query waiting for confirmation

import 'dart:async';
import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_sound/flutter_sound.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

import 'package:khaadim/app_config.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/providers/dine_in_provider.dart';
import 'package:khaadim/services/dine_in_service.dart';
import 'package:khaadim/utils/order_status_guest_copy.dart';
import 'package:khaadim/services/chat_service.dart';
import 'package:khaadim/services/conversation_memory.dart';
import 'package:khaadim/services/order_service.dart';
import 'package:khaadim/services/voice_command_service.dart';
import 'package:khaadim/services/voice_custom_deal_service.dart';
import 'package:khaadim/screens/payments/payment_method_screen.dart';
import 'package:khaadim/widgets/voice_nav_callbacks.dart';

const MethodChannel _speechChannel =
    MethodChannel('com.example.khaadim/speech');

// Simple yes/no words in both languages
const _YES_WORDS = [
  'yes',
  'yeah',
  'yep',
  'sure',
  'ok',
  'okay',
  'haan',
  'ha',
  'ji',
  'bilkul',
  'theek',
  'ہاں',
  'جی',
  'بالکل',
  'ٹھیک',
];
const _NO_WORDS = [
  'no',
  'nope',
  'nahi',
  'nai',
  'nہیں',
  'نہیں',
  'cancel',
  'kainsal',
];

class VoiceOrderHandler extends ChangeNotifier {
  final ChatService _chat = ChatService();
  late final VoiceCommandService _voiceCmd;
  final FlutterSoundRecorder _recorder = FlutterSoundRecorder();
  final FlutterTts _tts = FlutterTts();
  final AudioPlayer _gttsPlayer = AudioPlayer();
  late final VoiceCustomDealService _customDeal;

  // ── Conversation memory ───────────────────────────────────
  final ConversationMemory _memory = ConversationMemory();

  // When VoiceDealService sets suggestCustom=true we store the
  // pending query here. If user says "yes" next turn, we run it.
  String? _pendingCustomDealQuery;

  bool _isRecording = false;
  bool _isProcessing = false;
  bool _isUrdu = true;
  bool _recorderReady = false;
  bool _ttsReady = false;
  bool _voiceInitialized = false;

  String _lastAnnouncedMessage = '';
  DateTime _lastAnnouncementTime = DateTime.now();

  // Mutable so the screen can inject the real dine-in session ID.
  String _sessionId = 'session_${DateTime.now().millisecondsSinceEpoch}';
  DineInAddItemCallback? _pendingDineInAddItemCallback;

  VoiceNavCallbacks? _nav;

  bool get isRecording => _isRecording;
  bool get isProcessing => _isProcessing;
  bool get isUrdu => _isUrdu;

  void setNavCallbacks(VoiceNavCallbacks callbacks) => _nav = callbacks;

  /// Optional interceptor for checkout-specific voice commands.
  /// Called with the raw transcript before the generic voice pipeline.
  /// If it returns true the generic pipeline is skipped entirely.
  bool Function(String transcript)? _checkoutInterceptor;
  void setCheckoutInterceptor(bool Function(String transcript) fn) {
    _checkoutInterceptor = fn;
  }

  /// Speaks [text] with on-device [FlutterTts]. [lang] should be 'ur' or 'en'.
  Future<void> speakDirectly(String text, {String lang = 'ur'}) async {
    await _speak(text, language: lang);
  }

  /// Inject the DineInProvider.addItem callback so voice commands add items
  /// to the dine-in session order rather than the delivery CartProvider.
  void setDineInAddItemCallback(DineInAddItemCallback callback) {
    _pendingDineInAddItemCallback = callback;
    if (_voiceInitialized) {
      _voiceCmd.setDineInAddItemCallback(callback);
    }
  }

  /// Update the session ID used for LLM conversation memory.
  /// Call this whenever the dine-in session ID changes.
  void updateSessionId(String sessionId) {
    if (sessionId.isNotEmpty) _sessionId = sessionId;
  }

  Future<void> init() async {
    // Deal / command flows use the same on-device TTS as the main handler.
    _customDeal = VoiceCustomDealService(
      _tts,
      speaker: (text, {language}) =>
          _speak(text, language: language, awaitCompletion: false),
    );
    _voiceCmd = VoiceCommandService(onSpeak: (t) => _speak(t));
    _voiceInitialized = true;
    if (_pendingDineInAddItemCallback != null) {
      _voiceCmd.setDineInAddItemCallback(_pendingDineInAddItemCallback!);
    }
    await _initTTS();
    await _initRecorder();
  }

  Future<void> _initTTS() async {
    try {
      await _tts.setPitch(1.0);
      await _tts.setSpeechRate(0.45);
      await _tts.setVolume(1.0);
      await _applyTTSLang();
      _tts.setCompletionHandler(() {});
      _tts.setErrorHandler((msg) {
        _lastAnnouncedMessage = '';
      });
      _ttsReady = true;
    } catch (_) {
      _ttsReady = false;
    }
  }

  Future<void> _applyTTSLang() async {
    if (_isUrdu) {
      final langs = await _tts.getLanguages as List?;
      final hasUrdu = langs?.any((l) {
            final s = l.toString().toLowerCase();
            return s.contains('ur') || s.contains('urdu');
          }) ??
          false;
      await _tts.setLanguage(hasUrdu ? 'ur-PK' : 'en-US');
    } else {
      await _tts.setLanguage('en-US');
    }
  }

  Future<void> _initRecorder() async {
    final ok = await Permission.microphone.request();
    if (!ok.isGranted) return;
    await _recorder.openRecorder();
    _recorderReady = true;
  }

  Future<void> toggleLanguage() async {
    _isUrdu = !_isUrdu;
    await _applyTTSLang();
    notifyListeners();
  }

  Future<void> onMicDown(BuildContext context) async {
    if (_isProcessing || _isRecording) return;
    await _tts.stop();
    await _gttsPlayer.stop();
    _lastAnnouncedMessage = '';
    HapticFeedback.mediumImpact();
    _isUrdu ? await _startWhisper(context) : await _startNativeSTT(context);
  }

  Future<void> onMicUp(BuildContext context) async {
    if (!_isRecording) return;
    HapticFeedback.lightImpact();
    if (_isUrdu) await _stopWhisper(context);
  }

  Future<void> onMicCancel() async {
    if (!_isRecording) return;
    if (_isUrdu) await _recorder.stopRecorder();
    _isRecording = false;
    notifyListeners();
  }

  // ── Urdu recording ────────────────────────────────────────
  Future<void> _startWhisper(BuildContext context) async {
    if (!_recorderReady) {
      _snackError(context, _msgMicPermission());
      return;
    }
    final dir = await getTemporaryDirectory();
    final path =
        '${dir.path}/khaadim_${DateTime.now().millisecondsSinceEpoch}.wav';
    try {
      await _recorder.startRecorder(
        toFile: path,
        codec: Codec.pcm16WAV,
        sampleRate: 16000,
        numChannels: 1,
      );
      _isRecording = true;
      notifyListeners();
    } catch (_) {
      _snackError(context, _msgMicStartFailed());
    }
  }

  Future<void> _stopWhisper(BuildContext context) async {
    final path = await _recorder.stopRecorder();
    _isRecording = false;
    notifyListeners();
    if (path == null) return;

    final file = File(path);
    if (!await file.exists() || await file.length() < 5000) {
      if (await file.exists()) await file.delete();
      _snackError(context, _msgRecordingTooShort());
      return;
    }
    await _processUrduAudio(context, file);
  }

  Future<void> _processUrduAudio(BuildContext context, File file) async {
    _isProcessing = true;
    notifyListeners();
    try {
      // Pass last 10 turns to backend for context
      final voiceRes = await _chat.sendVoiceMessage(
        _sessionId,
        file,
        'voice',
        'ur',
        conversationHistory: _memory.toApiHistory(),
      );
      final transcript = ChatService.extractTranscript(voiceRes);

      if (transcript.isEmpty) {
        _snackError(context, _msgNoTranscript());
        return;
      }

      // Store user turn BEFORE executing
      _memory.add(role: 'user', text: transcript);

      // ── Context-window yes/no detection ──────────────────
      // If last assistant turn was a deal offer and user says yes/no
      if (_pendingCustomDealQuery != null) {
        final lower = transcript.toLowerCase().trim();
        final isYes = _YES_WORDS.any((w) => lower.contains(w));
        final isNo = _NO_WORDS.any((w) => lower.contains(w));

        if (isYes) {
          final query = _pendingCustomDealQuery!;
          _pendingCustomDealQuery = null;
          await _runCustomDealFlow(context, query);
          return;
        }
        if (isNo) {
          _pendingCustomDealQuery = null;
          final msg = _isUrdu ? 'ٹھیک ہے، کوئی بات نہیں۔' : 'No problem!';
          _memory.add(role: 'assistant', text: msg);
          await _speak(msg);
          return;
        }
        // Not yes/no — fall through to normal command processing
        _pendingCustomDealQuery = null;
      }

      // Checkout-screen interceptor: handles COD/card/place-order commands
      // directly without going through the full backend pipeline.
      if (_checkoutInterceptor != null && _checkoutInterceptor!(transcript)) {
        return; // fully handled
      }

      // Global interceptor for order status and payment cards
      if (await _handleGlobalVoiceCommands(context, transcript)) {
        return;
      }

      await _executeFromResponse(context, transcript, voiceRes);
    } on ChatServiceException catch (e, st) {
      debugPrint('[VoiceOrderHandler] ChatServiceException: $e\n$st');
      _snackError(context, _msgErrConnection());
    } catch (e, st) {
      debugPrint(
          '[VoiceOrderHandler] Unexpected error in _processUrduAudio: $e\n$st');
      _snackError(context, _msgErrGeneric());
    } finally {
      if (await file.exists()) await file.delete();
      _isProcessing = false;
      notifyListeners();
    }
  }

  // ── English STT ───────────────────────────────────────────
  Future<void> _startNativeSTT(BuildContext context) async {
    _isRecording = true;
    notifyListeners();
    try {
      final text = await _speechChannel
          .invokeMethod<String>('startSpeech', {'locale': 'en-US'});
      _isRecording = false;
      notifyListeners();
      if (text != null && text.trim().isNotEmpty) {
        _memory.add(role: 'user', text: text.trim());
        _snackInfo(
          context,
          _isUrdu ? 'سنا گیا: $text' : 'Heard: $text',
        );

        // Context-window yes/no detection (English path)
        if (_pendingCustomDealQuery != null) {
          final lower = text.toLowerCase().trim();
          final isYes = _YES_WORDS.any((w) => lower.contains(w));
          final isNo = _NO_WORDS.any((w) => lower.contains(w));

          if (isYes) {
            final query = _pendingCustomDealQuery!;
            _pendingCustomDealQuery = null;
            await _runCustomDealFlow(context, query);
            return;
          }
          if (isNo) {
            _pendingCustomDealQuery = null;
            final msg = 'No problem!';
            _memory.add(role: 'assistant', text: msg);
            await _speak(msg);
            return;
          }
          _pendingCustomDealQuery = null;
        }

        // Checkout-screen interceptor for English commands.
        if (_checkoutInterceptor != null &&
            _checkoutInterceptor!(text.trim())) {
          return; // fully handled
        }

        // Global interceptor for order status and payment cards
        if (await _handleGlobalVoiceCommands(context, text.trim())) {
          return;
        }

        await _runCommand(context, text.trim());
      } else {
        _snackError(context, _msgNoSpeechHeard());
      }
    } on PlatformException catch (e, st) {
      _isRecording = false;
      notifyListeners();
      debugPrint('[VoiceOrderHandler] PlatformException speech: $e\n$st');
      _snackError(context, _msgSpeechNotAvailable());
    } catch (_, st) {
      _isRecording = false;
      notifyListeners();
      debugPrint('[VoiceOrderHandler] Native STT error\n$st');
      _snackError(context, _msgErrGeneric());
    }
  }

  // ── Execute helpers ───────────────────────────────────────
  Future<void> _executeFromResponse(
    BuildContext context,
    String transcript,
    Map<String, dynamic> voiceRes,
  ) async {
    _isProcessing = true;
    notifyListeners();
    try {
      final result = await _voiceCmd.executeFromResponse(
        transcript: transcript,
        response: voiceRes,
        context: context,
        sessionId: _sessionId,
        language: 'ur',
        nav: _nav,
        memory: _memory,
      );
      await _handleResult(context, result, originalTranscript: transcript);
    } catch (e, st) {
      debugPrint('[VoiceOrderHandler] _executeFromResponse error: $e\n$st');
      _snackError(context, _msgErrGeneric());
    } finally {
      _isProcessing = false;
      notifyListeners();
    }
  }

  Future<void> _runCommand(BuildContext context, String transcript) async {
    _isProcessing = true;
    notifyListeners();
    try {
      final result = await _voiceCmd.execute(
        transcript: transcript,
        context: context,
        sessionId: _sessionId,
        language: 'en',
        nav: _nav,
        memory: _memory,
      );
      await _handleResult(context, result, originalTranscript: transcript);
    } catch (e, st) {
      debugPrint('[VoiceOrderHandler] _runCommand error: $e\n$st');
      _snackError(context, _msgErrGeneric());
    } finally {
      _isProcessing = false;
      notifyListeners();
    }
  }

  Future<bool> _handleGlobalVoiceCommands(
      BuildContext context, String transcript) async {
    final t = transcript.toLowerCase().trim();

    // 1. Check for Add Card / Card Payment
    final isNewCard = t.contains('new card') ||
        t.contains('naya card') ||
        t.contains('add card') ||
        t.contains('نیا کارڈ');

    final isCard =
        t.contains('card') || t.contains('کارڈ') || t.contains('online');

    if (isNewCard || isCard) {
      await speakDirectly(
          isNewCard ? 'نیا کارڈ شامل کریں۔' : 'کارڈ پیمنٹ سیکشن کھول رہا ہوں۔',
          lang: 'ur');
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (context.mounted) {
          Navigator.push(context,
              MaterialPageRoute(builder: (_) => const PaymentMethodsScreen()));
        }
      });
      return true;
    }

    // 2. Check for Order Status
    final isStatus = t.contains('status') ||
        t.contains('progress') ||
        t.contains('track') ||
        t.contains('time') ||
        t.contains('kitni dair') ||
        t.contains('waqt') ||
        t.contains('time left') ||
        t.contains('kahan');

    if (isStatus) {
      await _fetchAndSpeakOrderStatus(context);
      return true;
    }

    return false;
  }

  Future<void> _fetchAndSpeakOrderStatus(BuildContext context) async {
    try {
      // Kiosk: use table session orders, not delivery "my orders".
      if (AppConfig.isKiosk && context.mounted) {
        try {
          final dineIn =
              Provider.of<DineInProvider>(context, listen: false);
          final sid = (dineIn.sessionId ?? '').trim();
          if (sid.isNotEmpty) {
            final tableOrders =
                await DineInService().fetchSessionOrders(
              sid,
              token: dineIn.token,
            );
            if (tableOrders.isNotEmpty) {
              final m = tableOrders.last;
              final ks =
                  (m['kitchen_status'] ?? m['status'] ?? '').toString();
              final eta =
                  (m['estimated_prep_time_minutes'] as num?)?.toInt() ?? 0;
              final friendly = friendlyDineInKitchenLine(ks, ur: true);
              final etaBit =
                  eta > 0 ? ' تقریباً $eta منٹ لگ سکتے ہیں۔' : '';
              await speakDirectly('$friendly$etaBit', lang: 'ur');
              return;
            }
            await speakDirectly(
                'ابھی ٹیبل پر کوئی فعال آرڈر نہیں۔',
                lang: 'ur');
            return;
          }
        } catch (_) {
          // Fall through to delivery path.
        }
      }

      final res = await OrderService.getMyOrders();
      final orders = (res['orders'] as List?) ?? [];

      final activeOrder = orders.firstWhere(
        (o) => !['completed', 'cancelled']
            .contains(o['status'].toString().toLowerCase()),
        orElse: () => null,
      );

      if (activeOrder == null) {
        await speakDirectly('آپ کا کوئی ایکٹو آرڈر نہیں ہے۔', lang: 'ur');
        return;
      }

      final status = activeOrder['status'].toString().toLowerCase();
      final prepTime =
          (activeOrder['estimated_prep_time_minutes'] as num?)?.toInt() ?? 15;

      String timeStr;
      final base = prepTime > 0 ? prepTime : 15;
      if (status == 'confirmed' || status == 'in_kitchen') {
        timeStr = '$base منٹ';
      } else if (status == 'preparing') {
        final left = (base - 3).clamp(1, 99);
        timeStr = '$left منٹ';
      } else if (status == 'ready') {
        final left = (base ~/ 6).clamp(1, 99);
        timeStr = '$left منٹ';
      } else {
        timeStr = '$base منٹ';
      }

      String urduMsg;
      if (status == 'ready') {
        urduMsg = 'آپ کا آرڈر تیار ہے۔';
      } else if (status == 'preparing' || status == 'in_kitchen') {
        urduMsg = 'آپ کا آرڈر تیار ہو رہا ہے۔ تقریباً $timeStr لگیں گے۔';
      } else {
        urduMsg = 'تقریباً $timeStr باقی ہیں۔';
      }

      await speakDirectly(urduMsg, lang: 'ur');
    } catch (e) {
      await speakDirectly('آرڈر چیک کرنے میں مسئلہ ہوا۔', lang: 'ur');
    }
  }

  Future<void> _handleResult(
    BuildContext context,
    VoiceCommandResult result, {
    String originalTranscript = '',
  }) async {
    if (!result.success) {
      _snackError(context, _msgErrConnection());
      return;
    }

    if ((result.intentLine ?? '').trim().isNotEmpty) {
      _snackVoiceServerRouting(
        context,
        originalTranscript,
        result.intentLine!.trim(),
      );
    } else if (originalTranscript.trim().isNotEmpty) {
      _snackInfo(
        context,
        _isUrdu ? 'آپ نے کہا: $originalTranscript' : 'You said: $originalTranscript',
      );
    }

    // Save assistant reply to memory
    if (result.reply.isNotEmpty) {
      _memory.add(role: 'assistant', text: result.reply);
    }

    final action = result.actionTaken;

    if (result.navigated) {
      if (result.reply.isNotEmpty) {
        await _speak(result.reply);
      }
      return;
    }

    if (action == 'custom_deal') {
      // Prefer the canonical cleaned query the backend already extracted
      // (e.g. "create chinese deal for 2 people"). Falls back to the raw
      // mic transcript only when the backend couldn't normalize it.
      final cleanedQuery = result.transcript.trim();
      final fallback = originalTranscript.trim();
      final dealQuery = cleanedQuery.isNotEmpty ? cleanedQuery : fallback;
      await _runCustomDealFlow(context, dealQuery);
      return;
    }

    // Deal search returned suggest_custom — store for next turn
    if (action == 'deal_suggest_custom') {
      _pendingCustomDealQuery = result.transcript;
      await _speak(result.reply);
      return;
    }

    if (action == 'order_status') {
      await _speak(result.reply);
      return;
    }
    if (action == 'menu_inquiry') {
      await _speak(result.reply);
      return;
    }

    if (action == 'added_to_cart') {
      await _speak(result.reply);
      // Navigate to cart so the user can see the item(s) they just added.
      // Small delay lets TTS start speaking before the screen transitions.
      await Future.delayed(const Duration(milliseconds: 400));
      _nav?.openCart();
      return;
    }

    if (action == 'removed_from_cart' ||
        action == 'quantity_changed' ||
        action == 'cart_cleared') {
      await _speak(result.reply);
      return;
    }

    if (action == 'item_not_found') {
      _snackError(context, _isUrdu ? 'آئٹم نہیں ملا' : 'Item not found');
      return;
    }

    if (action.startsWith('favourites_')) {
      await _speak(result.reply);
      return;
    }

    if (result.reply.isNotEmpty) await _speak(result.reply);
  }

  // ── Custom deal flow ──────────────────────────────────────
  Future<void> _runCustomDealFlow(
      BuildContext context, String userQuery) async {
    if (userQuery.isEmpty) {
      final q = _isUrdu ? 'کس طرح کی ڈیل چاہیے؟' : 'What kind of deal?';
      _memory.add(role: 'assistant', text: q);
      await _speak(q);
      return;
    }
    _isProcessing = true;
    notifyListeners();
    try {
      final result = await _customDeal.createDeal(
        userQuery: userQuery,
        context: context,
        language: _isUrdu ? 'ur' : 'en',
      );
      if (result.needsClarification) {
        if (result.clarificationQuestion.isNotEmpty) {
          _memory.add(role: 'assistant', text: result.clarificationQuestion);
          _pendingCustomDealQuery = userQuery;
        }
        if (context.mounted) {
          _snackInfo(context,
              _isUrdu ? 'جواب دیں اور دوبارہ بولیں' : 'Answer and speak again');
        }
        return;
      }
      if (result.addedToCart) {
        final msg = _isUrdu
            ? 'ڈیل کارٹ میں شامل ہو گئی'
            : 'Deal added to cart';
        _memory.add(role: 'assistant', text: msg);
        if (context.mounted) {
          _snackInfo(context, msg);
          // CartProvider.sync is delivery-mode only; in Kiosk we use
          // DineInProvider instead. Guard the call so a missing cart in
          // kiosk doesn't throw ProviderNotFoundException and trigger the
          // generic "kharabi" error popup up the chain.
          try {
            Provider.of<CartProvider>(context, listen: false).sync();
          } catch (e) {
            debugPrint('[VoiceOrderHandler] CartProvider.sync skipped: $e');
          }
        }
      } else if (result.error.isNotEmpty) {
        if (context.mounted) {
          _snackError(context, _friendlyDealError(result.error));
        }
      }
    } catch (e, st) {
      debugPrint('[VoiceOrderHandler] _runCustomDealFlow error: $e\n$st');
      if (context.mounted) {
        _snackError(context, _msgDealFailed());
      }
    } finally {
      _isProcessing = false;
      notifyListeners();
    }
  }

  // ── TTS (on-device only — production-friendly, no second network voice) ──
  bool _isSpeaking = false;

  Future<void> _speak(
    String text, {
    String? language,
    bool awaitCompletion = true,
  }) async {
    final clean = _sanitizeForSpeech(text);
    if (clean.isEmpty) return;
    if (!_ttsReady) {
      debugPrint('[VoiceOrderHandler] FlutterTts not ready');
      return;
    }

    final now = DateTime.now();
    if (clean == _lastAnnouncedMessage &&
        now.difference(_lastAnnouncementTime).inSeconds < 10) {
      return;
    }

    if (_isSpeaking) {
      await _tts.stop();
      await _gttsPlayer.stop();
    }
    _isSpeaking = true;

    if (_isProcessing) {
      _isProcessing = false;
      notifyListeners();
    }

    try {
      await _gttsPlayer.stop();
      await _tts.stop();

      if (language == 'en') {
        await _tts.setLanguage('en-US');
      } else if (language == 'ur') {
        final langs = await _tts.getLanguages as List?;
        final hasUrdu = langs?.any((l) {
              final s = l.toString().toLowerCase();
              return s.contains('ur') || s.contains('urdu');
            }) ??
            false;
        await _tts.setLanguage(hasUrdu ? 'ur-PK' : 'en-US');
      } else if (_isUrdu) {
        await _applyTTSLang();
      } else {
        await _tts.setLanguage('en-US');
      }

      await _tts.speak(clean);
      if (awaitCompletion) {
        await _tts.awaitSpeakCompletion(true);
      } else {
        await _tts.awaitSpeakCompletion(false);
      }

      _lastAnnouncedMessage = clean;
      _lastAnnouncementTime = now;
    } catch (e, st) {
      debugPrint('[VoiceOrderHandler] FlutterTts failed: $e\n$st');
    } finally {
      _isSpeaking = false;
    }
  }

  // --- User-facing copy (no raw exceptions in UI) -------------------------

  String _msgErrConnection() => _isUrdu
      ? 'انٹرنیٹ یا سرور تک رسائی نہیں — دوبارہ کوشش کریں'
      : 'Can’t reach the server. Check your connection and try again.';

  String _msgErrGeneric() => _isUrdu
      ? 'مسئلہ ہوا — دوبارہ کوشش کریں'
      : 'Something went wrong. Please try again.';

  String _msgMicPermission() => _isUrdu
      ? 'مائیکروفون کی اجازت درکار ہے'
      : 'Microphone permission is required';

  String _msgMicStartFailed() => _isUrdu
      ? 'مائیک شروع نہیں ہو سکا — دوبارہ کوشش کریں'
      : 'Couldn’t start the microphone. Try again.';

  String _msgRecordingTooShort() => _isUrdu
      ? 'ریکارڈنگ بہت چھوٹی ہے — دوبارہ بولیں'
      : 'Recording was too short. Try again.';

  String _msgNoTranscript() => _isUrdu
      ? 'وائس سمجھ نہیں آئی — دوبارہ بولیں'
      : 'Couldn’t understand. Please speak again.';

  String _msgNoSpeechHeard() => _isUrdu
      ? 'کچھ سنائی نہیں دیا'
      : 'Nothing was heard';

  String _msgSpeechNotAvailable() => _isUrdu
      ? 'اس ڈیوائس پر اسپیچ سروس دستیاب نہیں'
      : 'Speech recognition isn’t available on this device';

  String _msgDealFailed() => _isUrdu
      ? 'ڈیل مکمل نہیں ہو سکی — دوبارہ کوشش کریں'
      : 'Couldn’t complete the deal. Try again.';

  String _friendlyDealError(String raw) {
    final t = raw.toLowerCase();
    if (t.contains('socket') ||
        t.contains('host lookup') ||
        t.contains('connection refused') ||
        t.contains('connection reset') ||
        t.contains('timeout') ||
        t.contains('network')) {
      return _msgErrConnection();
    }
    return _msgDealFailed();
  }

  /// Removes markdown decorations (`**`, `__`, `#`, backticks, bullets) and
  /// emojis so text-to-speech reads a natural sentence instead of announcing
  /// every stray symbol. Uses a manual codepoint filter rather than a
  /// supplementary-plane regex so it never throws on any Dart SDK.
  String _sanitizeForSpeech(String input) {
    if (input.isEmpty) return input;
    var s = input;

    s = s.replaceAll(RegExp(r'```[\s\S]*?```'), ' ');
    s = s.replaceAll(RegExp(r'`([^`]*)`'), r' $1 ');
    s = s.replaceAllMapped(
      RegExp(r'\[([^\]]+)\]\([^)]*\)'),
      (m) => m.group(1) ?? '',
    );
    // Dart's RegExp does NOT accept the inline `(?m)` flag — the engine is
    // ECMA-based and throws FormatException. Use `multiLine: true` instead.
    // Previously this crashed inside _speak and the surrounding catch
    // surfaced the generic "kharabi, dubara koshish karein" popup, so every
    // voice reply appeared silent.
    s = s.replaceAll(RegExp(r'^\s*#{1,6}\s+', multiLine: true), '');
    s = s.replaceAll(RegExp(r'^\s*[-*•]\s+', multiLine: true), '');
    s = s.replaceAll(RegExp(r'[*_~`#>]+'), ' ');
    s = s.replaceAll('×', ' x ');

    final buf = StringBuffer();
    for (final rune in s.runes) {
      if (_isPictographOrSymbol(rune)) {
        buf.write(' ');
      } else {
        buf.writeCharCode(rune);
      }
    }
    s = buf.toString();

    s = s.replaceAll(RegExp(r'\s+'), ' ').trim();
    return s;
  }

  bool _isPictographOrSymbol(int rune) {
    if (rune >= 0x2600 && rune <= 0x27BF) return true;
    if (rune >= 0x1F000 && rune <= 0x1FAFF) return true;
    if (rune == 0x200D || rune == 0xFE0F) return true;
    return false;
  }

  void _snackInfo(BuildContext context, String msg) {
    if (!context.mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(msg, maxLines: 1, overflow: TextOverflow.ellipsis),
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
      ));
  }

  /// Server routing: NLP intent + tool chain (same JSON as `/voice_chat` / `/chat`).
  void _snackVoiceServerRouting(
    BuildContext context,
    String said,
    String intentBlock,
  ) {
    if (!context.mounted) return;
    final line1 =
        _isUrdu ? 'آپ نے کہا: $said' : 'You said: $said';
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                line1,
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              Text(
                intentBlock,
                style: TextStyle(
                  fontSize: 13,
                  color: Colors.white.withValues(alpha: 0.92),
                ),
              ),
            ],
          ),
          duration: const Duration(seconds: 6),
          behavior: SnackBarBehavior.floating,
        ),
      );
  }

  void _snackError(BuildContext context, String msg) {
    if (!context.mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(msg, maxLines: 1, overflow: TextOverflow.ellipsis),
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
        backgroundColor: Colors.redAccent,
      ));
  }

  @override
  void dispose() {
    _recorder.closeRecorder();
    _gttsPlayer.stop();
    _gttsPlayer.dispose();
    _tts.stop();
    super.dispose();
  }
}

// lib/services/conversation_memory.dart
// NEW FILE — place in lib/services/
//
// Ring buffer storing last 10 voice conversation turns.
// Passed to every /chat and /voice_chat call so backend has context.
//
// Key feature: lastTurnWasDealOffer lets VoiceOrderHandler detect
// when user says "ہاں"/"yes" after "want custom deal?" offer.

class ConversationTurn {
  final String   role;      // 'user' | 'assistant'
  final String   text;
  final DateTime timestamp;

  const ConversationTurn({
    required this.role,
    required this.text,
    required this.timestamp,
  });

  Map<String, String> toJson() => {'role': role, 'content': text};
}

class ConversationMemory {
  static const int _max = 10;
  final List<ConversationTurn> _turns = [];

  // ── Write ─────────────────────────────────────────────────
  void add({required String role, required String text}) {
    if (text.trim().isEmpty) return;
    _turns.add(ConversationTurn(
      role: role, text: text.trim(), timestamp: DateTime.now(),
    ));
    if (_turns.length > _max) _turns.removeRange(0, _turns.length - _max);
  }

  // ── Read ──────────────────────────────────────────────────
  List<ConversationTurn> getLast([int n = _max]) {
    final count = n.clamp(0, _turns.length);
    return List.unmodifiable(_turns.sublist(_turns.length - count));
  }

  /// Serialised for backend — pass as conversation_history field
  List<Map<String, String>> toApiHistory([int n = _max]) =>
      getLast(n).map((t) => t.toJson()).toList();

  int  get length     => _turns.length;
  bool get isEmpty    => _turns.isEmpty;
  bool get isNotEmpty => _turns.isNotEmpty;

  String get lastAssistantText {
    for (int i = _turns.length - 1; i >= 0; i--) {
      if (_turns[i].role == 'assistant') return _turns[i].text;
    }
    return '';
  }

  String get lastUserText {
    for (int i = _turns.length - 1; i >= 0; i--) {
      if (_turns[i].role == 'user') return _turns[i].text;
    }
    return '';
  }

  /// True when last assistant message was a deal suggestion/offer
  /// Used to detect "ہاں"/"yes" as confirmation
  bool get lastTurnWasDealOffer {
    final last = lastAssistantText.toLowerCase();
    return last.contains('deal') || last.contains('ڈیل') ||
        last.contains('custom') || last.contains('کسٹم') ||
        last.contains('create') || last.contains('بناؤں');
  }

  void clear() => _turns.clear();
}
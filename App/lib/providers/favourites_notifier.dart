// lib/providers/favourites_notifier.dart
//
// A thin app-wide notifier for favourite state.
// UI cards (menu, deals) listen to this so they instantly
// reflect voice-driven add/remove without a full reload.

import 'package:flutter/foundation.dart';

class FavouritesNotifier extends ChangeNotifier {
  // ── Singleton ────────────────────────────────────────────────
  FavouritesNotifier._();
  static final FavouritesNotifier instance = FavouritesNotifier._();

  // Separate sets for menu items and catalog deals
  final Set<int> _itemIds = {};
  final Set<int> _dealIds = {};

  // ── Public read helpers ─────────────────────────────────────
  bool isItemFav(int itemId) => _itemIds.contains(itemId);
  bool isDealFav(int dealId) => _dealIds.contains(dealId);

  // ── Called by voice pipeline after a successful toggle ──────
  /// Mark [itemId] (menu item) as added or removed.
  /// [added] == true → it is now a favourite; false → removed.
  void updateItem(int itemId, {required bool added}) {
    if (added) {
      _itemIds.add(itemId);
    } else {
      _itemIds.remove(itemId);
    }
    notifyListeners();
  }

  /// Mark [dealId] (catalog deal) as added or removed.
  void updateDeal(int dealId, {required bool added}) {
    if (added) {
      _dealIds.add(dealId);
    } else {
      _dealIds.remove(dealId);
    }
    notifyListeners();
  }

  // ── Called on startup / refresh to pre-seed known favourites ─
  void seedItems(Iterable<int> ids) {
    _itemIds
      ..clear()
      ..addAll(ids);
    notifyListeners();
  }

  void seedDeals(Iterable<int> ids) {
    _dealIds
      ..clear()
      ..addAll(ids);
    notifyListeners();
  }
}

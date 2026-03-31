import 'dart:async';

import 'package:flutter/material.dart';
import 'package:khaadim/services/dine_in_session_storage.dart';

class DineInProvider extends ChangeNotifier {
  String? sessionId;
  String? tableNumber;
  String? tableId;
  String? token;
  List<Map<String, dynamic>> currentOrderItems = [];
  bool isLoading = false;

  void startSession(
    String sessionId,
    String tableId,
    String tableNumber, {
    String? token,
  }) {
    this.sessionId = sessionId;
    this.tableId = tableId;
    this.tableNumber = tableNumber;
    this.token = token;
    currentOrderItems.clear();
    unawaited(_persistSession(sessionId, tableId, tableNumber, token));
    notifyListeners();
  }

  Future<void> _persistSession(
    String sessionId,
    String tableId,
    String tableNumber,
    String? token,
  ) async {
    try {
      await DineInSessionStorage.saveSession(
        sessionId: sessionId,
        tableId: tableId,
        tableNumber: tableNumber,
        token: token,
      );
    } catch (_) {
      // Ignore persistence errors and keep in-memory session active.
    }
  }

  Future<bool> restoreSession() async {
    final saved = await DineInSessionStorage.getSession();
    if (saved == null) {
      return false;
    }

    sessionId = saved['session_id'];
    tableId = saved['table_id'];
    tableNumber = saved['table_number'];
    final restoredToken = saved['token'];
    token = (restoredToken == null || restoredToken.isEmpty) ? null : restoredToken;
    currentOrderItems.clear();
    notifyListeners();
    return true;
  }

  void addItem(
    int itemId,
    String itemType,
    String itemName,
    double price,
    int quantity,
  ) {
    final index = currentOrderItems.indexWhere(
      (item) => item['item_id'] == itemId && item['item_type'] == itemType,
    );

    if (index >= 0) {
      final existingQuantity =
          (currentOrderItems[index]['quantity'] as num?)?.toInt() ?? 0;
      currentOrderItems[index]['quantity'] = existingQuantity + quantity;
      currentOrderItems[index]['item_name'] = itemName;
      currentOrderItems[index]['price'] = price;
    } else {
      currentOrderItems.add({
        'item_id': itemId,
        'item_type': itemType,
        'item_name': itemName,
        'price': price,
        'quantity': quantity,
      });
    }

    notifyListeners();
  }

  void addCustomDeal({
    required int customDealId,
    required String title,
    required double totalPrice,
    required int groupSize,
    required List<Map<String, dynamic>> bundleItems,
  }) {
    final normalizedBundle = bundleItems
        .map((raw) {
          final rawType = (raw['item_type'] ?? 'menu_item').toString();
          final normalizedType = rawType == 'deal' ? 'deal' : 'menu_item';
          final rawId = raw['item_id'];
          final rawQuantity = raw['quantity'];
          final rawPrice = raw['price'] ?? raw['item_price'] ?? raw['unit_price'];

          return {
            'item_id': rawId is int ? rawId : int.tryParse(rawId.toString()) ?? 0,
            'item_type': normalizedType,
            'item_name': (raw['item_name'] ?? 'Item').toString(),
            'quantity': rawQuantity is int
                ? rawQuantity
                : int.tryParse(rawQuantity.toString()) ?? 1,
            'price': rawPrice is num
                ? rawPrice.toDouble()
                : double.tryParse(rawPrice.toString()) ?? 0.0,
          };
        })
        .where(
          (item) =>
              (item['item_id'] as int) > 0 && (item['quantity'] as int) > 0,
        )
        .toList();

    currentOrderItems.add({
      'item_id': customDealId,
      'item_type': 'custom_deal',
      'item_name': title,
      'price': totalPrice,
      'quantity': 1,
      'group_size': groupSize,
      'is_quantity_locked': true,
      'bundle_items': normalizedBundle,
    });

    notifyListeners();
  }

  void removeItem(int itemId, String itemType) {
    currentOrderItems.removeWhere(
      (item) => item['item_id'] == itemId && item['item_type'] == itemType,
    );
    notifyListeners();
  }

  void clearOrder() {
    currentOrderItems.clear();
    notifyListeners();
  }

  void endSession() {
    sessionId = null;
    tableNumber = null;
    tableId = null;
    token = null;
    currentOrderItems.clear();
    isLoading = false;
    unawaited(_clearPersistedSession());
    notifyListeners();
  }

  Future<void> _clearPersistedSession() async {
    try {
      await DineInSessionStorage.clearSession();
    } catch (_) {
      // Ignore persistence errors while ending session.
    }
  }

  double get orderTotal {
    return currentOrderItems.fold(0.0, (sum, item) {
      final price = (item['price'] as num?)?.toDouble() ?? 0.0;
      final quantity = (item['quantity'] as num?)?.toInt() ?? 0;
      return sum + (price * quantity);
    });
  }
}
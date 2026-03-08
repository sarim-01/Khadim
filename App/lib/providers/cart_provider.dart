import 'package:flutter/material.dart';
import '../models/cart_item.dart';
import '../models/menu_item.dart';
import '../models/deal_model.dart';
import '../services/cart_service.dart';
import '../services/cart_storage.dart';

class CartProvider extends ChangeNotifier {
  final List<CartItem> _items = [];

  String? _cartId;
  bool _isSyncing = false;
  String? _error;

  List<CartItem> get items => _items;
  String? get cartId => _cartId;
  bool get isSyncing => _isSyncing;
  String? get error => _error;

  double get totalPrice =>
      _items.fold(0, (sum, item) => sum + (item.price * item.quantity));

  int get cartCount => _items.fold(0, (sum, item) => sum + item.quantity);

  /////// INIT CART ///////
  Future<void> initCart(String userId) async {
    _isSyncing = true;
    _error = null;
    notifyListeners();

    try {
      final res = await CartService.getOrCreateActiveCart();
      final serverCartId = (res["cart_id"] ?? "").toString();

      if (serverCartId.isEmpty) {
        throw Exception("Cart creation failed (missing cart_id)");
      }

      _cartId = serverCartId;
      await CartStorage.saveCartId(_cartId!);

      await sync();
    } catch (e) {
      _error = e.toString();
    } finally {
      _isSyncing = false;
      notifyListeners();
    }
  }

  /////// INTERNAL PARSER ///////
  void _applyCartResponse(Map<String, dynamic> res) {
    final data = res["data"] ?? res;

    final List<dynamic> serverItems =
    (data["items"] ?? data["cart_items"] ?? []) as List<dynamic>;

    _items
      ..clear()
      ..addAll(serverItems.map((x) {
        final m = x as Map<String, dynamic>;

        final itemId = (m["item_id"] ?? m["id"] ?? "").toString();
        final itemType = (m["item_type"] ?? m["type"] ?? "").toString();

        final unitPriceNum = m["unit_price"] ?? m["price"] ?? 0;
        final qtyNum = m["quantity"] ?? 1;

        return CartItem(
          id: "$itemType:$itemId",
          name: (m["item_name"] ?? m["name"] ?? "").toString(),
          title: (m["item_name"] ?? m["title"] ?? m["name"] ?? "").toString(),
          price: (unitPriceNum is num) ? unitPriceNum.toDouble() : 0.0,
          quantity: (qtyNum is num) ? qtyNum.toInt() : 1,
          type: itemType,
          image: (m["image_url"] ?? m["image"])?.toString(),
        );
      }));
  }

  /////// SYNC ///////
  Future<void> sync() async {
    if (_cartId == null) return;

    _isSyncing = true;
    _error = null;
    notifyListeners();

    try {
      final res = await CartService.getSummary(cartId: _cartId!);
      _applyCartResponse(res);
    } catch (e) {
      try {
        final res = await CartService.getOrCreateActiveCart();
        final newCartId = (res["cart_id"] ?? "").toString();

        if (newCartId.isNotEmpty) {
          _cartId = newCartId;
          await CartStorage.saveCartId(_cartId!);

          final res2 = await CartService.getSummary(cartId: _cartId!);
          _applyCartResponse(res2);

          _error = null;
          return;
        }
      } catch (_) {}

      _error = e.toString();
    } finally {
      _isSyncing = false;
      notifyListeners();
    }
  }

  /////// ADD MENU ITEM ///////
  Future<void> addMenuItem(MenuItemModel item) async {
    if (_cartId == null) return;

    await CartService.addItem(
      cartId: _cartId!,
      itemType: "menu_item",
      itemId: item.itemId,
      quantity: 1,
    );

    await sync();
  }

  /////// ADD DEAL ///////
  Future<void> addDeal(DealModel deal) async {
    if (_cartId == null) return;

    await CartService.addItem(
      cartId: _cartId!,
      itemType: "deal",
      itemId: deal.dealId,
      quantity: 1,
    );

    await sync();
  }

  /////// UPDATE QTY ///////
  Future<void> updateQty({
    required int itemId,
    required String itemType,
    required int quantity,
  }) async {
    if (_cartId == null) return;

    await CartService.setQuantity(
      cartId: _cartId!,
      itemType: itemType,
      itemId: itemId,
      quantity: quantity,
    );

    await sync();
  }

  /////// REMOVE ///////
  Future<void> removeById({
    required int itemId,
    required String itemType,
  }) async {
    if (_cartId == null) return;

    await CartService.removeItem(
      cartId: _cartId!,
      itemType: itemType,
      itemId: itemId,
    );

    await sync();
  }

  /////// AFTER ORDER SUCCESS ///////
  Future<void> refreshAfterOrderSuccess() async {
    _items.clear();
    _error = null;
    notifyListeners();

    final res = await CartService.getOrCreateActiveCart();
    final newCartId = (res["cart_id"] ?? "").toString();

    if (newCartId.isEmpty) {
      throw Exception("Failed to create a fresh cart after order");
    }

    _cartId = newCartId;
    await CartStorage.saveCartId(_cartId!);
    await sync();
  }

  /////// HARD RESET ///////
  void reset() {
    _items.clear();
    _cartId = null;
    _error = null;
    _isSyncing = false;
    notifyListeners();
  }
}
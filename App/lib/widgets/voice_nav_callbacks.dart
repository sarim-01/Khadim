class VoiceNavCallbacks {
  final void Function(int index) switchTab;
  final void Function({String? cuisine, String? category}) openMenuWithFilter;
  final void Function() openCart;
  final void Function({String paymentMethod}) openCheckout;
  final void Function() openOrders;
  final void Function() openFavourites;
  final void Function() openRecommendations;

  final void Function({
    String? cuisineFilter,
    String? servingFilter,
    int? highlightDealId,
  }) openDealsWithFilter;

  const VoiceNavCallbacks({
    required this.switchTab,
    required this.openMenuWithFilter,
    required this.openCart,
    required this.openCheckout,
    required this.openOrders,
    required this.openFavourites,
    required this.openRecommendations,
    required this.openDealsWithFilter,
  });
}

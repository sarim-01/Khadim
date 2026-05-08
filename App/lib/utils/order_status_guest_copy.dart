// Guest-facing kitchen lines (no raw enum labels for TTS/snackbars).

String friendlyDineInKitchenLine(String rawStatus, {required bool ur}) {
  final s =
      rawStatus.trim().toLowerCase().replaceAll(RegExp(r'[\s\-]+'), '_');
  bool has(String fragment) => s.contains(fragment);

  if (ur) {
    if (has('cancel')) return 'یہ آرڈر منسوخ ہو چکا ہے۔';
    if (has('ready') || has('served')) return 'آپ کا آرڈر تیار ہے۔';
    if (has('prep') || has('kitchen') || has('cook')) {
      return 'آپ کا آرڈر کچن میں تیار کیا جا رہا ہے۔';
    }
    if (has('confirm')) return 'آپ کا آرڈر قبول ہو چکا ہے۔';
    if (has('complet')) return 'یہ آرڈر مکمل ہو چکا ہے۔';
    return 'آپ کے آرڈر پر کام ہو رہا ہے۔';
  }
  if (has('cancel')) return 'That order was cancelled.';
  if (has('ready') || has('served')) return 'Your order is ready.';
  if (has('prep') || has('kitchen') || has('cook')) {
    return 'Your order is being prepared in the kitchen.';
  }
  if (has('confirm')) return 'Your order has been confirmed.';
  if (has('complet')) return 'That order is complete.';
  return 'We are working on your order.';
}

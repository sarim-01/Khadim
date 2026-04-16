enum AppFlavor { customer, kiosk, admin }

class AppConfig {
  static AppFlavor flavor = AppFlavor.customer;

  static bool get isKiosk    => flavor == AppFlavor.kiosk;
  static bool get isCustomer => flavor == AppFlavor.customer;
  static bool get isAdmin    => flavor == AppFlavor.admin;
}
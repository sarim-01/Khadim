import 'api_client.dart';

class OrderService {
  /////// GET MY ORDERS ///////
  static Future<Map<String, dynamic>> getMyOrders() async {
    return ApiClient.getJson(
      "/orders/my",
      auth: true,
      retryOnNetworkError: true,
    );
  }

  /////// GET ORDER DETAIL ///////
  static Future<Map<String, dynamic>> getOrderDetail({
    required int orderId,
  }) async {
    return ApiClient.getJson(
      "/orders/$orderId",
      auth: true,
      retryOnNetworkError: true,
    );
  }
}
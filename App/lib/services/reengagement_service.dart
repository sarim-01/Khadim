import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timezone/data/latest.dart' as tz;
import 'package:timezone/timezone.dart' as tz;
import 'package:permission_handler/permission_handler.dart';

import 'package:khaadim/models/app_notification_item.dart';
import 'package:khaadim/models/recommendation_result.dart';
import 'package:khaadim/services/favorites_service.dart';
import 'package:khaadim/services/personalization_service.dart';
import 'package:khaadim/services/api_client.dart';

class ReengagementService {
  ReengagementService._();
  static final ReengagementService instance = ReengagementService._();

  static const int _reengagementNotificationId = 91001;
  static const int _testInactivityDelayMinutes = 1;
  static const String _prefsInboxKey = 'reengagement_notification_inbox_v1';

  final FlutterLocalNotificationsPlugin _notifications =
      FlutterLocalNotificationsPlugin();

  final ValueNotifier<int> unreadCount = ValueNotifier<int>(0);

  String? _currentUserId;

  GlobalKey<NavigatorState>? _navigatorKey;
  String? _pendingHighlightItemName;
  int? _pendingHighlightItemId;

  Future<void> initialize(GlobalKey<NavigatorState> navigatorKey) async {
    _navigatorKey = navigatorKey;

    // Properly initialize timezones AND set the device's local timezone.
    // Without setLocalLocation(), tz.local defaults to UTC — causing all scheduled
    // notifications to fire at wrong times or be silently dropped.
    tz.initializeTimeZones();
    final String timeZoneName = await FlutterTimezone.getLocalTimezone();
    tz.setLocalLocation(tz.getLocation(timeZoneName));
    print('[Reengagement] ⏰ Timezone set to: $timeZoneName');

    const androidSettings =
        AndroidInitializationSettings('@mipmap/ic_launcher');
    const initSettings = InitializationSettings(android: androidSettings);

    await _notifications.initialize(
      initSettings,
      onDidReceiveNotificationResponse: (NotificationResponse response) async {
        await _handleNotificationTap(response.payload);
      },
    );

    final androidImpl = _notifications.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();

    // Request notification permission
    final bool? notifGranted =
        await androidImpl?.requestNotificationsPermission();
    print('[Reengagement] Notification permission granted: $notifGranted');

    // Request exact alarm permission (needed for exactAllowWhileIdle)
    final bool? exactGranted =
        await androidImpl?.requestExactAlarmsPermission();
    print('[Reengagement] Exact alarm permission granted: $exactGranted');

    // Use permission_handler as fallback for Android 13+
    final status = await Permission.notification.status;
    if (status.isDenied) {
      final requested = await Permission.notification.request();
      print('[Reengagement] Notification Requested: $requested');
    }

    await _refreshUnreadCount();
    print('[Reengagement] ✅ Initialization complete.');
  }

  void setUserId(String userId) {
    _currentUserId = userId;
  }

  Future<void> refreshAndSchedule({String? userId}) async {
    final activeUserId = userId ?? _currentUserId;
    if (activeUserId == null) return;

    final prefs = await SharedPreferences.getInstance();
    final now = DateTime.now();

    final lastOpenedIso =
        prefs.getString('reengagement_last_opened_$activeUserId');
    final lastOpened =
        lastOpenedIso != null ? DateTime.tryParse(lastOpenedIso) : null;
    await prefs.setString(
        'reengagement_last_opened_$activeUserId', now.toIso8601String());

    final inactivityHours =
        lastOpened == null ? 999 : now.difference(lastOpened).inHours;

    final favouritesPayload = await FavouritesService.getFavourites();
    final favCount = ((favouritesPayload['items'] as List?)?.length ?? 0) +
        ((favouritesPayload['deals'] as List?)?.length ?? 0) +
        ((favouritesPayload['custom_deals'] as List?)?.length ?? 0);

    double avgRating = 3.0; // default score
    try {
      final feedbackResponse = await ApiClient.getJson(
        '/feedback/me/average',
        auth: true,
        timeout: const Duration(seconds: 10),
      );
      if (feedbackResponse['average_rating'] != null) {
        avgRating = (feedbackResponse['average_rating'] as num).toDouble();
      }
    } catch (e) {
      print('[Reengagement] Failed to fetch average rating from DB: $e');
    }

    final engagementScore = _computeEngagementScore(
      favouritesCount: favCount,
      avgRating: avgRating,
      inactivityHours: inactivityHours,
    );

    final recResult = await PersonalizationService.getRecommendations(topK: 5);

    // Build a combined pool: top personalised picks + top deals + favourite menu items + favourite deals.
    // Favourites are already fetched above (favouritesPayload), so we reuse them.
    final List<RecommendedItem> pool = [...recResult.recommendedItems];

    // ── LLM Recommended Deals ─────────────────────────────────────────
    for (final d in recResult.recommendedDeals) {
      if (pool.any((r) => r.itemId == -d.dealId)) continue;
      pool.add(RecommendedItem(
        itemId: -d.dealId, // Negative ID space for deals
        itemName: d.dealName,
        score: d.score,
        reason: d.reason,
        source: d.source,
        category: 'deal',
      ));
    }

    // ── Favourite menu items ────────────────────────────────────────
    final rawFavItems = (favouritesPayload['items'] as List?) ?? [];
    for (final fav in rawFavItems) {
      if (fav is! Map<String, dynamic>) continue;
      final favId = (fav['item_id'] as num?)?.toInt();
      if (favId == null) continue;
      // Skip if already in pool (dedup by itemId)
      if (pool.any((r) => r.itemId == favId)) continue;
      pool.add(RecommendedItem(
        itemId: favId,
        itemName: (fav['item_name'] ?? '').toString(),
        score: 0.0,
        reason: 'One of your favourites',
        source: 'favourite',
        // 'category' is now returned by the API — use it for bread filtering
        category: (fav['category'] ?? 'fast_food').toString(),
      ));
    }

    // ── Favourite deals (use deal_id as itemId, deal_name as itemName) ─
    final rawFavDeals = (favouritesPayload['deals'] as List?) ?? [];
    for (final fav in rawFavDeals) {
      if (fav is! Map<String, dynamic>) continue;
      final dealId = (fav['deal_id'] as num?)?.toInt();
      if (dealId == null) continue;
      // Use a negative ID space to avoid collision with menu item IDs
      final poolId = -(dealId);
      if (pool.any((r) => r.itemId == poolId)) continue;
      pool.add(RecommendedItem(
        itemId: poolId,
        itemName: (fav['deal_name'] ?? '').toString(),
        score: 0.0,
        reason: 'A deal you love',
        source: 'favourite_deal',
        category: 'deal', // deals are never bread — always included
      ));
    }

    // Exclude bread items from notifications
    final filteredPool =
        pool.where((r) => r.category.toLowerCase() != 'bread').toList();

    // Pick randomly from the combined pool
    RecommendedItem? highlighted;
    if (filteredPool.isNotEmpty) {
      highlighted = filteredPool[Random().nextInt(filteredPool.length)];
    }

    // Cancel any previously scheduled notification before scheduling a new one
    await _notifications.cancel(_reengagementNotificationId);

    final title = _buildTitle(engagementScore);
    final body = _buildBody(engagementScore, highlighted);

    final payload = jsonEncode({
      'target_route': '/main',
      'item_id': highlighted?.itemId,
      'item_name': highlighted?.itemName,
      'kind': 'reengagement',
    });

    // Cancel any previously scheduled notification before scheduling a new one
    await cancelPending();

    // exactAllowWhileIdle fires even in Doze mode — much more reliable than inexact
    final details = NotificationDetails(
      android: AndroidNotificationDetails(
        'reengagement_channel',
        'Re-engagement',
        channelDescription: 'Inactivity and preference-based reminders',
        importance: Importance.max,
        priority: Priority.high,
        playSound: true,
        enableVibration: true,
      ),
    );

    final scheduleAt = tz.TZDateTime.now(tz.local).add(
      const Duration(minutes: _testInactivityDelayMinutes),
    );

    print(
        '[Reengagement] 🕐 Current local time: ${tz.TZDateTime.now(tz.local)}');
    print('[Reengagement] 🔔 Scheduling notification for: $scheduleAt');

    try {
      await _notifications.zonedSchedule(
        _reengagementNotificationId,
        title,
        body,
        scheduleAt,
        details,
        payload: payload,
        androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
      );
      print('[Reengagement] ✅ Notification scheduled successfully!');
      print('[Reengagement] 📝 Title: "$title" | Body: "$body"');
    } catch (e, stack) {
      print('[Reengagement] ❌ Failed to schedule notification: $e');
      print('[Reengagement] Stack: $stack');
    }

    await _appendInbox(
      AppNotificationItem(
        id: '${now.millisecondsSinceEpoch}',
        title: title,
        body: body,
        createdAt: now,
        isRead: false,
        targetRoute: '/main',
        itemId: highlighted?.itemId,
        itemName: highlighted?.itemName,
      ),
    );
  }

  Future<void> cancelPending() async {
    print(
        '[Reengagement] 🚫 Cancelling pending re-engagement notification (app opened)');
    await _notifications.cancel(_reengagementNotificationId);
  }

  Future<List<AppNotificationItem>> getInbox() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList(_prefsInboxKey) ?? const <String>[];
    final items = raw
        .map((e) => jsonDecode(e) as Map<String, dynamic>)
        .map(AppNotificationItem.fromJson)
        .toList()
      ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return items;
  }

  Future<void> markAllRead() async {
    final items = await getInbox();
    final updated = items.map((e) => e.copyWith(isRead: true)).toList();
    await _saveInbox(updated);
  }

  Future<void> openInboxItem(AppNotificationItem item) async {
    final items = await getInbox();
    final updated = items.map((e) {
      if (e.id == item.id) return e.copyWith(isRead: true);
      return e;
    }).toList();
    await _saveInbox(updated);

    _pendingHighlightItemId = item.itemId;
    _pendingHighlightItemName = item.itemName;

    final nav = _navigatorKey?.currentState;
    if (nav != null) {
      nav.pushNamedAndRemoveUntil('/main', (route) => false);
    }
  }

  String? consumePendingHighlightItemName() {
    final v = _pendingHighlightItemName;
    _pendingHighlightItemName = null;
    return v;
  }

  int? consumePendingHighlightItemId() {
    final v = _pendingHighlightItemId;
    _pendingHighlightItemId = null;
    return v;
  }

  int _computeEngagementScore({
    required int favouritesCount,
    required double avgRating,
    required int inactivityHours,
  }) {
    final favouritesScore = (favouritesCount * 8).clamp(0, 40);
    final ratingScore = ((avgRating / 5.0) * 40).round().clamp(0, 40);

    int inactivityScore;
    if (inactivityHours <= 6) {
      inactivityScore = 20;
    } else if (inactivityHours <= 24) {
      inactivityScore = 14;
    } else if (inactivityHours <= 48) {
      inactivityScore = 8;
    } else {
      inactivityScore = 2;
    }

    return (favouritesScore + ratingScore + inactivityScore).clamp(0, 100);
  }

  String _buildTitle(int score) {
    if (score < 45) return 'We miss you at Khaadim';
    if (score < 70) return 'A fresh pick is waiting for you';
    return 'Your favorites are ready again';
  }

  String _buildBody(int score, RecommendedItem? item) {
    final itemPart = item == null ? '' : ' Try ${item.itemName}.';
    if (score < 45) {
      return 'It has been a while. Come back for your next meal.$itemPart';
    }
    if (score < 70) {
      return 'Based on your tastes, we found something you may like.$itemPart';
    }
    return 'You have great taste. Your usual picks are waiting.$itemPart';
  }

  Future<void> _handleNotificationTap(String? payload) async {
    if (payload == null || payload.isEmpty) return;

    try {
      final data = jsonDecode(payload) as Map<String, dynamic>;
      _pendingHighlightItemId = (data['item_id'] as num?)?.toInt();
      _pendingHighlightItemName = data['item_name']?.toString();
    } catch (_) {
      _pendingHighlightItemId = null;
      _pendingHighlightItemName = null;
    }

    final nav = _navigatorKey?.currentState;
    if (nav != null) {
      nav.pushNamedAndRemoveUntil('/main', (route) => false);
    }
  }

  Future<void> _appendInbox(AppNotificationItem item) async {
    final items = await getInbox();
    items.insert(0, item);
    if (items.length > 50) {
      items.removeRange(50, items.length);
    }
    await _saveInbox(items);
  }

  Future<void> _saveInbox(List<AppNotificationItem> items) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = items.map((e) => jsonEncode(e.toJson())).toList();
    await prefs.setStringList(_prefsInboxKey, raw);
    await _refreshUnreadCount();
  }

  Future<void> _refreshUnreadCount() async {
    final items = await getInbox();
    unreadCount.value = items.where((e) => !e.isRead).length;
  }
}

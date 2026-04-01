import 'dart:async';

import 'package:flutter/material.dart';
import 'package:khaadim/services/api_client.dart';

class RestaurantManagementScreen extends StatefulWidget {
  const RestaurantManagementScreen({super.key});

  @override
  State<RestaurantManagementScreen> createState() =>
      _RestaurantManagementScreenState();
}

class _RestaurantManagementScreenState
    extends State<RestaurantManagementScreen> {
  static const Color _bg = Color(0xFF07090F);
  static const Color _surface = Color(0xFF0D111C);
  static const Color _border = Color(0xFF1A2035);
  static const Color _accent = Color(0xFF6366F1);

  int _selectedView = 0; // 0 = Live Status, 1 = Table Manager
  List<dynamic> _tables = [];
  bool _isLoading = true;
  Timer? _refreshTimer;
  final ScrollController _liveScrollController = ScrollController();
  final ScrollController _tableManagerScrollController = ScrollController();
  final ScrollController _tableManagerHorizontalScrollController =
      ScrollController();

  @override
  void initState() {
    super.initState();
    _loadTables();
    _refreshTimer = Timer.periodic(const Duration(seconds: 15), (_) {
      _loadTables();
    });
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _liveScrollController.dispose();
    _tableManagerScrollController.dispose();
    _tableManagerHorizontalScrollController.dispose();
    super.dispose();
  }

  Future<void> _loadTables() async {
    if (!mounted) return;
    setState(() => _isLoading = true);

    try {
      final response = await ApiClient.getJson('/admin/tables/all', auth: true);
      final dynamic raw = response['data'] ?? response;
      final List<dynamic> tables = raw is List<dynamic>
          ? raw
          : (response['tables'] as List<dynamic>? ?? []);

      if (!mounted) return;
      setState(() {
        _tables = tables;
        _isLoading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Failed to load restaurant tables'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  Future<Map<String, dynamic>> _fetchSessionDetail(String tableId) async {
    return ApiClient.getJson(
      '/admin/tables/$tableId/session-detail',
      auth: true,
    );
  }

  String _formatStatus(String? raw) {
    final value = (raw ?? '').trim();
    if (value.isEmpty) return 'Unknown';
    return value
        .split('_')
        .map(
          (part) => part.isEmpty
              ? part
              : '${part[0].toUpperCase()}${part.substring(1).toLowerCase()}',
        )
        .join(' ');
  }

  String _formatTimeShort(String? isoString) {
    if (isoString == null || isoString.isEmpty) return '--:--';
    final dt = DateTime.tryParse(isoString);
    if (dt == null) return '--:--';
    final local = dt.toLocal();
    final hh = local.hour.toString().padLeft(2, '0');
    final mm = local.minute.toString().padLeft(2, '0');
    return '$hh:$mm';
  }

  String _formatDateTimeWithAmPm(String? isoString) {
    if (isoString == null || isoString.isEmpty) return '-';
    final dt = DateTime.tryParse(isoString);
    if (dt == null) return '-';

    final local = dt.toLocal();
    final hour12 = local.hour % 12 == 0 ? 12 : local.hour % 12;
    final minute = local.minute.toString().padLeft(2, '0');
    final ampm = local.hour >= 12 ? 'PM' : 'AM';
    final day = local.day.toString().padLeft(2, '0');
    final month = local.month.toString().padLeft(2, '0');
    final year = local.year;
    return '$day/$month/$year  $hour12:$minute $ampm';
  }

  String _formatDurationSince(String? isoString) {
    if (isoString == null || isoString.isEmpty) return '-';
    final dt = DateTime.tryParse(isoString);
    if (dt == null) return '-';

    final diff = DateTime.now().difference(dt.toLocal());
    final hours = diff.inHours;
    final minutes = diff.inMinutes % 60;
    if (hours > 0) {
      return '${hours}h ${minutes}m';
    }
    return '${diff.inMinutes}m';
  }

  Color _statusTextColor(String status) {
    switch (status) {
      case 'available':
        return Colors.greenAccent;
      case 'occupied':
        return Colors.amber;
      case 'bill_requested_cash':
        return Colors.orange;
      case 'cleaning':
        return Colors.white38;
      default:
        return _accent;
    }
  }

  Color _statusBackgroundColor(String status) {
    switch (status) {
      case 'available':
        return const Color(0xFF0A1A12);
      case 'occupied':
        return const Color(0xFF2D1F0E);
      case 'bill_requested_cash':
        return const Color(0xFF2D1A0E);
      case 'cleaning':
        return const Color(0xFF1A1A1A);
      default:
        return const Color(0xFF13183A);
    }
  }

  Widget _buildStatusBadge(String status) {
    final pretty = _formatStatus(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: _statusBackgroundColor(status),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        pretty,
        style: TextStyle(
          color: _statusTextColor(status),
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  Future<void> _showSessionDetailSheet(Map<String, dynamic> table) async {
    final tableId = table['table_id']?.toString() ?? '';
    if (tableId.isEmpty) return;

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: _surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (context) {
        return DraggableScrollableSheet(
          expand: false,
          initialChildSize: 0.85,
          minChildSize: 0.55,
          maxChildSize: 0.95,
          builder: (context, scrollController) {
            return FutureBuilder<Map<String, dynamic>>(
              future: _fetchSessionDetail(tableId),
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                }

                if (!snapshot.hasData || snapshot.hasError) {
                  return Center(
                    child: Text(
                      'Failed to load session details',
                      style: const TextStyle(color: Colors.white70),
                    ),
                  );
                }

                final detail = snapshot.data!;
                final orders = detail['orders'] as List<dynamic>? ?? [];
                final total =
                    (detail['total_amount'] as num?)?.toDouble() ?? 0.0;
                final startedAt = detail['started_at']?.toString();

                return Container(
                  decoration: BoxDecoration(
                    color: _surface,
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(16),
                    ),
                    border: Border.all(color: _border),
                  ),
                  child: ListView(
                    controller: scrollController,
                    padding: const EdgeInsets.fromLTRB(18, 16, 18, 24),
                    children: [
                      Text(
                        'Table ${detail['table_number']}',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 22,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Started: ${_formatDateTimeWithAmPm(startedAt)}',
                        style: const TextStyle(
                          color: Colors.white54,
                          fontSize: 12,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'Duration: ${_formatDurationSince(startedAt)}',
                        style: const TextStyle(
                          color: Colors.white70,
                          fontSize: 12,
                        ),
                      ),
                      const SizedBox(height: 16),
                      for (final dynamic orderRaw in orders)
                        ..._buildOrderDetailBlock(
                          orderRaw as Map<String, dynamic>,
                        ),
                      const SizedBox(height: 14),
                      Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: const Color(0xFF13183A),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: _border),
                        ),
                        child: Text(
                          'Grand Total: Rs. ${total.toStringAsFixed(0)}',
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 20,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              },
            );
          },
        );
      },
    );
  }

  List<Widget> _buildOrderDetailBlock(Map<String, dynamic> order) {
    final round = (order['round_number'] as num?)?.toInt() ?? 0;
    final subtotal = (order['total_price'] as num?)?.toDouble() ?? 0.0;
    final items = order['items'] as List<dynamic>? ?? [];

    return [
      const Divider(color: _border, height: 22),
      Text(
        'Round $round',
        style: const TextStyle(
          color: _accent,
          fontSize: 16,
          fontWeight: FontWeight.w700,
        ),
      ),
      const SizedBox(height: 8),
      if (items.isEmpty)
        const Text(
          'No items in this round.',
          style: TextStyle(color: Colors.white54, fontSize: 12),
        )
      else
        for (final dynamic itemRaw in items)
          _buildOrderLine(itemRaw as Map<String, dynamic>),
      const SizedBox(height: 8),
      Align(
        alignment: Alignment.centerRight,
        child: Text(
          'Subtotal: Rs. ${subtotal.toStringAsFixed(0)}',
          style: const TextStyle(
            color: Colors.white70,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    ];
  }

  Widget _buildOrderLine(Map<String, dynamic> item) {
    final name = (item['name'] ?? '-').toString();
    final qty = (item['quantity'] as num?)?.toInt() ?? 0;
    final lineTotal = (item['line_total'] as num?)?.toDouble() ?? 0.0;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Text(
        '$name × $qty  —  Rs. ${lineTotal.toStringAsFixed(0)}',
        style: const TextStyle(color: Colors.white70, fontSize: 13),
      ),
    );
  }

  Future<void> _regeneratePin(String tableId) async {
    try {
      final data = await ApiClient.postJson(
        '/admin/tables/$tableId/regenerate-pin',
        body: {},
        auth: true,
      );
      if (!mounted) return;
      await _loadTables();
      if (!mounted) return;
      final pin = data['new_pin']?.toString() ?? '------';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('PIN updated: $pin'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to regenerate PIN: $e'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  Future<void> _deleteTable(String tableId) async {
    try {
      await ApiClient.deleteJson('/admin/tables/$tableId', auth: true);
      if (!mounted) return;
      await _loadTables();
    } on ApiException catch (e) {
      if (!mounted) return;
      final message = e.message.isNotEmpty
          ? e.message
          : 'Cannot delete an occupied table';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message), behavior: SnackBarBehavior.floating),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Cannot delete an occupied table'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  Future<void> _showAddTableDialog() async {
    final controller = TextEditingController();

    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          backgroundColor: _surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
          title: const Text(
            'Add New Table',
            style: TextStyle(color: Colors.white),
          ),
          content: TextField(
            controller: controller,
            keyboardType: TextInputType.number,
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              hintText: 'Enter table number',
              hintStyle: const TextStyle(color: Colors.white38),
              filled: true,
              fillColor: const Color(0xFF13183A),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: const BorderSide(color: _border),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: const BorderSide(color: _border),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: const BorderSide(color: _accent),
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text(
                'Cancel',
                style: TextStyle(color: Colors.white54),
              ),
            ),
            TextButton(
              onPressed: () async {
                final value = int.tryParse(controller.text.trim());
                if (value == null) {
                  if (!mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('Please enter a valid table number'),
                      behavior: SnackBarBehavior.floating,
                    ),
                  );
                  return;
                }

                try {
                  final result = await ApiClient.postJson(
                    '/admin/tables/create',
                    body: {'table_number': value},
                    auth: true,
                  );
                  if (!mounted) return;
                  if (!dialogContext.mounted) return;

                  Navigator.of(dialogContext).pop();
                  await _loadTables();
                  if (!mounted) return;

                  final tableNo =
                      result['table_number']?.toString() ?? value.toString();
                  final pin = result['table_pin']?.toString() ?? '------';

                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('Table $tableNo created. PIN: $pin'),
                      behavior: SnackBarBehavior.floating,
                    ),
                  );
                } on ApiException catch (e) {
                  if (!mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(e.message),
                      behavior: SnackBarBehavior.floating,
                    ),
                  );
                } catch (e) {
                  if (!mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('Failed to create table: $e'),
                      behavior: SnackBarBehavior.floating,
                    ),
                  );
                }
              },
              child: const Text('Create', style: TextStyle(color: _accent)),
            ),
          ],
        );
      },
    );
  }

  Widget _buildLiveStatusView() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final isDesktop = constraints.maxWidth > 1100;
        final crossAxisCount = isDesktop ? 4 : 2;
        final ratio = isDesktop ? 1.3 : 1.1;

        return Scrollbar(
          controller: _liveScrollController,
          thumbVisibility: true,
          child: GridView.builder(
            controller: _liveScrollController,
            padding: const EdgeInsets.all(16),
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: crossAxisCount,
              childAspectRatio: ratio,
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
            ),
            itemCount: _tables.length,
            itemBuilder: (context, index) {
              final table = _tables[index] as Map<String, dynamic>;
              final status = (table['status'] ?? '').toString();
              final hasActiveSession = table['session_id'] != null;
              final hasWaiterCall = table['pending_waiter_call'] == true;
              final total = (table['total_amount'] as num?)?.toDouble() ?? 0.0;
              final rounds = (table['round_count'] as num?)?.toInt() ?? 0;
              final since = _formatTimeShort(table['started_at']?.toString());

              return InkWell(
                borderRadius: BorderRadius.circular(10),
                onTap: hasActiveSession
                    ? () => _showSessionDetailSheet(table)
                    : null,
                child: Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: _surface,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: _border, width: 1),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              'Table ${table['table_number']}',
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 20,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Flexible(
                            child: Align(
                              alignment: Alignment.centerRight,
                              child: FittedBox(
                                fit: BoxFit.scaleDown,
                                child: _buildStatusBadge(status),
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      if (hasWaiterCall)
                        const Row(
                          children: [
                            Icon(
                              Icons.notifications_active,
                              color: Colors.redAccent,
                              size: 16,
                            ),
                            Text(
                              ' Waiter called',
                              style: TextStyle(
                                color: Colors.redAccent,
                                fontSize: 11,
                              ),
                            ),
                          ],
                        ),
                      if (status == 'occupied' ||
                          status == 'bill_requested_cash') ...[
                        const SizedBox(height: 8),
                        Text(
                          'Since: $since',
                          style: const TextStyle(
                            color: Colors.white54,
                            fontSize: 12,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          'Total: Rs. ${total.toStringAsFixed(0)}',
                          style: const TextStyle(
                            color: Colors.white70,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          'Rounds: $rounds',
                          style: const TextStyle(
                            color: Colors.white54,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              );
            },
          ),
        );
      },
    );
  }

  Widget _buildPinMask(String tableId, String pin) {
    return StatefulBuilder(
      builder: (context, setInnerState) {
        final hiddenState = _pinHidden[tableId] ?? true;
        return Wrap(
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 4,
          runSpacing: 2,
          children: [
            Text(
              hiddenState ? '●●●●●●' : pin,
              style: const TextStyle(color: Colors.white70, fontSize: 13),
            ),
            IconButton(
              onPressed: () {
                _pinHidden[tableId] = !hiddenState;
                setInnerState(() {});
              },
              style: IconButton.styleFrom(
                minimumSize: const Size(24, 24),
                padding: EdgeInsets.zero,
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                visualDensity: VisualDensity.compact,
              ),
              icon: Icon(
                hiddenState ? Icons.visibility : Icons.visibility_off,
                color: Colors.white54,
                size: 18,
              ),
              splashRadius: 16,
            ),
          ],
        );
      },
    );
  }

  Widget _buildActionTextButton({
    required String label,
    required Color color,
    required VoidCallback onPressed,
  }) {
    return TextButton(
      onPressed: onPressed,
      style: TextButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        minimumSize: const Size(0, 30),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        visualDensity: VisualDensity.compact,
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  final Map<String, bool> _pinHidden = {};

  Widget _buildTableManagerView() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final isDesktop = constraints.maxWidth > 1100;

        return Stack(
          children: [
            Positioned.fill(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: isDesktop
                    ? Container(
                        decoration: BoxDecoration(
                          color: _surface,
                          border: Border.all(color: _border),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        padding: const EdgeInsets.fromLTRB(12, 12, 12, 86),
                        child: Scrollbar(
                          controller: _tableManagerScrollController,
                          thumbVisibility: true,
                          trackVisibility: true,
                          child: SingleChildScrollView(
                            controller: _tableManagerScrollController,
                            physics: const AlwaysScrollableScrollPhysics(),
                            child: Scrollbar(
                              controller:
                                  _tableManagerHorizontalScrollController,
                              thumbVisibility: true,
                              trackVisibility: true,
                              notificationPredicate: (notification) {
                                return notification.metrics.axis ==
                                    Axis.horizontal;
                              },
                              child: SingleChildScrollView(
                                controller:
                                    _tableManagerHorizontalScrollController,
                                scrollDirection: Axis.horizontal,
                                physics: const AlwaysScrollableScrollPhysics(),
                                child: DataTable(
                                  columnSpacing: 24,
                                  horizontalMargin: 12,
                                  headingRowHeight: 46,
                                  dataRowMinHeight: 72,
                                  dataRowMaxHeight: 112,
                                  dividerThickness: 0.8,
                                  headingRowColor: WidgetStateProperty.all(
                                    const Color(0xFF13183A),
                                  ),
                                  dataRowColor: WidgetStateProperty.all(
                                    _surface,
                                  ),
                                  columns: const [
                                    DataColumn(
                                      label: Text(
                                        'TABLE',
                                        style: TextStyle(color: Colors.white70),
                                      ),
                                    ),
                                    DataColumn(
                                      label: Text(
                                        'PIN',
                                        style: TextStyle(color: Colors.white70),
                                      ),
                                    ),
                                    DataColumn(
                                      label: Text(
                                        'STATUS',
                                        style: TextStyle(color: Colors.white70),
                                      ),
                                    ),
                                    DataColumn(
                                      label: Text(
                                        'ACTIONS',
                                        style: TextStyle(color: Colors.white70),
                                      ),
                                    ),
                                  ],
                                  rows: _tables.map((dynamic rowRaw) {
                                    final row = rowRaw as Map<String, dynamic>;
                                    final tableId =
                                        row['table_id']?.toString() ?? '';
                                    final pin =
                                        row['table_pin']?.toString() ?? '';
                                    final status =
                                        row['status']?.toString() ?? '';

                                    return DataRow(
                                      cells: [
                                        DataCell(
                                          ConstrainedBox(
                                            constraints: const BoxConstraints(
                                              minWidth: 90,
                                              maxWidth: 150,
                                            ),
                                            child: Text(
                                              'Table ${row['table_number']}',
                                              overflow: TextOverflow.ellipsis,
                                              style: const TextStyle(
                                                color: Colors.white,
                                                fontWeight: FontWeight.w600,
                                              ),
                                            ),
                                          ),
                                        ),
                                        DataCell(_buildPinMask(tableId, pin)),
                                        DataCell(
                                          ConstrainedBox(
                                            constraints: const BoxConstraints(
                                              maxWidth: 180,
                                            ),
                                            child: Align(
                                              alignment: Alignment.centerLeft,
                                              child: FittedBox(
                                                fit: BoxFit.scaleDown,
                                                alignment: Alignment.centerLeft,
                                                child: _buildStatusBadge(
                                                  status,
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                        DataCell(
                                          ConstrainedBox(
                                            constraints: const BoxConstraints(
                                              minWidth: 150,
                                              maxWidth: 220,
                                            ),
                                            child: Align(
                                              alignment: Alignment.centerLeft,
                                              child: Wrap(
                                                spacing: 4,
                                                runSpacing: 4,
                                                children: [
                                                  _buildActionTextButton(
                                                    label: 'Regen PIN',
                                                    color: _accent,
                                                    onPressed: () =>
                                                        _regeneratePin(tableId),
                                                  ),
                                                  _buildActionTextButton(
                                                    label: 'Delete',
                                                    color: Colors.redAccent,
                                                    onPressed: () =>
                                                        _deleteTable(tableId),
                                                  ),
                                                ],
                                              ),
                                            ),
                                          ),
                                        ),
                                      ],
                                    );
                                  }).toList(),
                                ),
                              ),
                            ),
                          ),
                        ),
                      )
                    : Scrollbar(
                        controller: _tableManagerScrollController,
                        thumbVisibility: true,
                        trackVisibility: true,
                        child: ListView.builder(
                          controller: _tableManagerScrollController,
                          padding: const EdgeInsets.only(bottom: 96),
                          itemCount: _tables.length,
                          itemBuilder: (context, index) {
                            final row = _tables[index] as Map<String, dynamic>;
                            final tableId = row['table_id']?.toString() ?? '';
                            final pin = row['table_pin']?.toString() ?? '';
                            final status = row['status']?.toString() ?? '';

                            return Container(
                              margin: const EdgeInsets.only(bottom: 12),
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                color: _surface,
                                borderRadius: BorderRadius.circular(10),
                                border: Border.all(color: _border),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Expanded(
                                        child: Text(
                                          'Table ${row['table_number']}',
                                          overflow: TextOverflow.ellipsis,
                                          style: const TextStyle(
                                            color: Colors.white,
                                            fontWeight: FontWeight.w600,
                                            fontSize: 16,
                                          ),
                                        ),
                                      ),
                                      const SizedBox(width: 8),
                                      Flexible(
                                        child: Align(
                                          alignment: Alignment.centerRight,
                                          child: FittedBox(
                                            fit: BoxFit.scaleDown,
                                            child: _buildStatusBadge(status),
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 10),
                                  Wrap(
                                    crossAxisAlignment:
                                        WrapCrossAlignment.center,
                                    spacing: 4,
                                    runSpacing: 4,
                                    children: [
                                      const Text(
                                        'PIN: ',
                                        style: TextStyle(
                                          color: Colors.white54,
                                          fontSize: 13,
                                        ),
                                      ),
                                      _buildPinMask(tableId, pin),
                                    ],
                                  ),
                                  const SizedBox(height: 8),
                                  Wrap(
                                    spacing: 8,
                                    runSpacing: 6,
                                    children: [
                                      _buildActionTextButton(
                                        label: 'Regen PIN',
                                        color: _accent,
                                        onPressed: () =>
                                            _regeneratePin(tableId),
                                      ),
                                      _buildActionTextButton(
                                        label: 'Delete',
                                        color: Colors.redAccent,
                                        onPressed: () => _deleteTable(tableId),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                      ),
              ),
            ),
            Positioned(
              right: 24,
              bottom: 24,
              child: FloatingActionButton.extended(
                onPressed: _showAddTableDialog,
                backgroundColor: _accent,
                icon: const Icon(Icons.add, color: Colors.white),
                label: const Text(
                  'Add Table',
                  style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildViewToggle() {
    Widget chip({
      required int index,
      required String label,
      required String emoji,
    }) {
      final selected = _selectedView == index;
      return Expanded(
        child: InkWell(
          onTap: () {
            if (_selectedView == index) return;
            setState(() => _selectedView = index);
            _loadTables();
          },
          borderRadius: BorderRadius.circular(10),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOut,
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
            decoration: BoxDecoration(
              color: selected ? const Color(0xFF13183A) : Colors.transparent,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: selected ? _accent : _border),
            ),
            child: Text(
              '$emoji  $label',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: selected ? _accent : Colors.white54,
                fontWeight: FontWeight.w600,
                fontSize: 13,
              ),
            ),
          ),
        ),
      );
    }

    return Container(
      margin: const EdgeInsets.fromLTRB(16, 14, 16, 0),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: _surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: _border),
      ),
      child: Row(
        children: [
          chip(index: 0, label: 'Live Status', emoji: '🟢'),
          const SizedBox(width: 10),
          chip(index: 1, label: 'Table Manager', emoji: '🪑'),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: _bg,
      child: Column(
        children: [
          _buildViewToggle(),
          Expanded(
            child: _selectedView == 0
                ? _buildLiveStatusView()
                : _buildTableManagerView(),
          ),
        ],
      ),
    );
  }
}

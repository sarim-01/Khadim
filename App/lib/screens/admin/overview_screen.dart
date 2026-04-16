import 'dart:async';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:khaadim/services/api_client.dart';

class OverviewScreen extends StatefulWidget {
  const OverviewScreen({super.key});

  @override
  State<OverviewScreen> createState() => _OverviewScreenState();
}

class _OverviewScreenState extends State<OverviewScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _animController;
  late Animation<double> _pulseAnimation;

  bool _isLoading = true;
  int _todayOrders = 0;
  double _todayRevenue = 0.0;
  double _avgOrderValue = 0.0;
  int _activeOrders = 0;

  double _ordersDelta = 0.0;
  double _revenueDelta = 0.0;
  double _aovDelta = 0.0;

  List<Map<String, dynamic>> _revenueData = [];
  List<Map<String, dynamic>> _categoryData = [];

  bool _isLoadingOrders = true;
  List<dynamic> _recentOrders = [];
  int _ordersDaysFilter = 7;
  int _ordersCurrentPage = 0;
  static const int _ordersPerPage = 20;
  final Set<int> _expandedOrderIds = {};

  Timer? _pollingTimer;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 1),
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.3, end: 1.0).animate(
      CurvedAnimation(parent: _animController, curve: Curves.easeInOut),
    );

    _fetchOverviewData();

    // Poll every 10 seconds for real-time dashboard updates
    _pollingTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      _fetchOverviewData(isRefresh: true);
    });
  }

  @override
  void dispose() {
    _pollingTimer?.cancel();
    _animController.dispose();
    super.dispose();
  }

  Future<void> _fetchOverviewData({bool isRefresh = false}) async {
    if (!isRefresh && mounted) {
      setState(() => _isLoading = true);
    }

    _fetchRecentOrders(isRefresh: isRefresh);

    try {
      final data = await ApiClient.getJson('/admin/overview', auth: true);
      if (mounted) {
        setState(() {
          _todayOrders = data['today_orders'] ?? 0;
          _todayRevenue = (data['today_revenue'] ?? 0.0).toDouble();
          _avgOrderValue = (data['avg_order_value'] ?? 0.0).toDouble();
          _activeOrders = data['active_orders'] ?? 0;

          _ordersDelta = (data['orders_delta'] ?? 0.0).toDouble();
          _revenueDelta = (data['revenue_delta'] ?? 0.0).toDouble();
          _aovDelta = (data['aov_delta'] ?? 0.0).toDouble();

          final rawRev = data['revenue_chart_data'] as List<dynamic>? ?? [];
          _revenueData = rawRev.map((e) => e as Map<String, dynamic>).toList();

          final rawCat = data['category_sales_data'] as List<dynamic>? ?? [];
          _categoryData = rawCat.map((e) => e as Map<String, dynamic>).toList();

          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isLoading = false);
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Failed to load overview: $e')));
      }
    }
  }

  String _formatDelta(double delta) {
    if (delta > 0) return '↑ ${delta.toStringAsFixed(1)}% vs yesterday';
    if (delta < 0) return '↓ ${delta.abs().toStringAsFixed(1)}% vs yesterday';
    return '${delta.toStringAsFixed(1)}% vs yesterday';
  }

  Color _getDeltaColor(double delta) {
    if (delta > 0) return Colors.greenAccent;
    if (delta < 0) return Colors.redAccent;
    return Colors.white54;
  }

  String _formatAmountNoDecimals(double value) {
    return value.round().toString();
  }

  Future<void> _fetchRecentOrders({bool isRefresh = false}) async {
    if (!isRefresh && mounted) setState(() => _isLoadingOrders = true);
    try {
      final data = await ApiClient.getJson(
        '/admin/orders?days=$_ordersDaysFilter',
        auth: true,
      );
      if (mounted) {
        setState(() {
          _recentOrders = data['orders'] ?? [];
          _isLoadingOrders = false;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _isLoadingOrders = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Column(
        children: [
          Container(
            color: const Color(0xFF0D111C),
            child: const TabBar(
              indicatorColor: Color(0xFF6366F1),
              labelColor: Colors.white,
              unselectedLabelColor: Colors.white54,
              tabs: [
                Tab(text: 'Summary'),
                Tab(text: 'Recent Orders'),
              ],
            ),
          ),
          Expanded(
            child: TabBarView(
              children: [_buildSummaryTab(context), _buildRecentOrdersTab()],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSummaryTab(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final isDesktop = constraints.maxWidth > 1100;
        return SingleChildScrollView(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Overview',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 24),

              // KPI Cards
              if (isDesktop)
                Row(
                  children: [
                    Expanded(
                      child: _buildKpiCard(
                        'Today\'s Revenue',
                        'Rs ${_formatAmountNoDecimals(_todayRevenue)}',
                        _formatDelta(_revenueDelta),
                        _getDeltaColor(_revenueDelta),
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: _buildKpiCard(
                        'Orders Today',
                        '$_todayOrders',
                        _formatDelta(_ordersDelta),
                        _getDeltaColor(_ordersDelta),
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: _buildKpiCard(
                        'Average Order Value',
                        'Rs ${_formatAmountNoDecimals(_avgOrderValue)}',
                        _formatDelta(_aovDelta),
                        _getDeltaColor(_aovDelta),
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(child: _buildActiveOrdersCard()),
                  ],
                )
              else
                LayoutBuilder(
                  builder: (context, constraints) {
                    final cardWidth = (constraints.maxWidth - 16) / 2;
                    return Wrap(
                      spacing: 16,
                      runSpacing: 16,
                      children: [
                        SizedBox(
                          width: cardWidth,
                          child: _buildKpiCard(
                            'Today\'s Revenue',
                            'Rs ${_formatAmountNoDecimals(_todayRevenue)}',
                            _formatDelta(_revenueDelta),
                            _getDeltaColor(_revenueDelta),
                          ),
                        ),
                        SizedBox(
                          width: cardWidth,
                          child: _buildKpiCard(
                            'Orders Today',
                            '$_todayOrders',
                            _formatDelta(_ordersDelta),
                            _getDeltaColor(_ordersDelta),
                          ),
                        ),
                        SizedBox(
                          width: cardWidth,
                          child: _buildKpiCard(
                            'Avg Order Value',
                            'Rs ${_formatAmountNoDecimals(_avgOrderValue)}',
                            _formatDelta(_aovDelta),
                            _getDeltaColor(_aovDelta),
                          ),
                        ),
                        SizedBox(
                          width: cardWidth,
                          child: _buildActiveOrdersCard(),
                        ),
                      ],
                    );
                  },
                ),

              const SizedBox(height: 24),

              // Charts Area
              if (isDesktop)
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(flex: 2, child: _buildLineChartCard()),
                    const SizedBox(width: 16),
                    Expanded(flex: 1, child: _buildDonutChartCard()),
                  ],
                )
              else
                Column(
                  children: [
                    _buildLineChartCard(),
                    const SizedBox(height: 16),
                    _buildDonutChartCard(),
                  ],
                ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildKpiCard(
    String title,
    String value,
    String delta,
    Color deltaColor,
  ) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFF0D111C),
        border: Border.all(color: const Color(0xFF1A2035), width: 1),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              title,
              style: const TextStyle(color: Colors.white54, fontSize: 14),
            ),
          ),
          const SizedBox(height: 12),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              value,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 28,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            delta,
            style: TextStyle(
              color: deltaColor,
              fontSize: 11,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActiveOrdersCard() {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFF0D111C),
        border: Border.all(color: const Color(0xFF1A2035), width: 1),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              'Active Orders',
              style: TextStyle(color: Colors.white54, fontSize: 14),
            ),
          ),
          const SizedBox(height: 12),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Row(
              children: [
                Text(
                  '$_activeOrders',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(width: 12),
                FadeTransition(
                  opacity: _pulseAnimation,
                  child: Container(
                    width: 12,
                    height: 12,
                    decoration: const BoxDecoration(
                      color: Colors.greenAccent,
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'In kitchen now',
            style: TextStyle(
              color: Colors.white54,
              fontSize: 11,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLineChartCard() {
    // Calculate dynamic maxY
    double maxRev = 10.0;
    for (var r in _revenueData) {
      final rev = (r['revenue'] ?? 0).toDouble();
      if (rev > maxRev) maxRev = rev;
    }
    // Add 20% padding to the top
    maxRev = (maxRev * 1.2).ceilToDouble();

    // Generate spots
    final spots = <FlSpot>[];
    for (int i = 0; i < _revenueData.length; i++) {
      spots.add(
        FlSpot(i.toDouble(), (_revenueData[i]['revenue'] ?? 0).toDouble()),
      );
    }

    // If no data, provide a dummy spot so it doesn't crash
    if (spots.isEmpty) {
      spots.add(const FlSpot(0, 0));
      maxRev = 10;
    }

    return Container(
      height: 350,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFF0D111C),
        border: Border.all(color: const Color(0xFF1A2035), width: 1),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Revenue Over Time (Last 7 Days)',
            style: TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 32),
          Expanded(
            child: LineChart(
              LineChartData(
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  getDrawingHorizontalLine: (value) =>
                      const FlLine(color: Colors.white10, strokeWidth: 1),
                ),
                titlesData: FlTitlesData(
                  show: true,
                  rightTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  topTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 30,
                      interval: 1,
                      getTitlesWidget: (value, meta) {
                        final index = value.toInt();
                        if (index >= 0 && index < _revenueData.length) {
                          return Padding(
                            padding: const EdgeInsets.only(top: 8.0),
                            child: Text(
                              _revenueData[index]['day'] ?? '',
                              style: const TextStyle(
                                color: Colors.white54,
                                fontSize: 10,
                              ),
                            ),
                          );
                        }
                        return const Text('');
                      },
                    ),
                  ),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      interval: (maxRev / 5).ceilToDouble() == 0
                          ? 1
                          : (maxRev / 5).ceilToDouble(),
                      reservedSize: 42,
                      getTitlesWidget: (value, meta) {
                        return Text(
                          value.toInt().toString(),
                          style: const TextStyle(
                            color: Colors.white54,
                            fontSize: 12,
                          ),
                        );
                      },
                    ),
                  ),
                ),
                borderData: FlBorderData(show: false),
                minX: 0,
                maxX: (_revenueData.length - 1).toDouble() < 0
                    ? 0
                    : (_revenueData.length - 1).toDouble(),
                minY: 0,
                maxY: maxRev,
                lineBarsData: [
                  LineChartBarData(
                    spots: spots,
                    isCurved: true,
                    color: const Color(0xFF6366F1), // Accent color
                    barWidth: 3,
                    isStrokeCapRound: true,
                    dotData: const FlDotData(show: false),
                    belowBarData: BarAreaData(
                      show: true,
                      color: const Color(0xFF6366F1).withOpacity(0.15),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDonutChartCard() {
    double totalRevenue = 0.0;
    for (var c in _categoryData) {
      totalRevenue += (c['revenue'] ?? 0).toDouble();
    }

    final colors = [
      const Color(0xFF6366F1),
      const Color(0xFF10B981),
      const Color(0xFFF59E0B),
      const Color(0xFFEC4899),
      const Color(0xFF6B7280),
      const Color(0xFF3B82F6),
      const Color(0xFF8B5CF6),
    ];

    List<PieChartSectionData> sections = [];
    List<Widget> legendItems = [];

    for (int i = 0; i < _categoryData.length; i++) {
      final cat = _categoryData[i];
      final rev = (cat['revenue'] ?? 0).toDouble();
      final catName = cat['category'] ?? 'Unknown';

      double percentage = 0;
      if (totalRevenue > 0) {
        percentage = (rev / totalRevenue) * 100;
      }

      final color = colors[i % colors.length];

      sections.add(
        PieChartSectionData(
          color: color,
          value: percentage,
          title: percentage > 5 ? '${percentage.toInt()}%' : '',
          radius: 30,
          titleStyle: const TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.bold,
            color: Colors.white,
          ),
        ),
      );

      legendItems.add(
        _buildLegendItem(color, '$catName (${percentage.toStringAsFixed(1)}%)'),
      );
    }

    if (sections.isEmpty) {
      sections.add(
        PieChartSectionData(
          color: Colors.white10,
          value: 100,
          title: 'No Data',
        ),
      );
    }

    return Container(
      height: 350,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFF0D111C),
        border: Border.all(color: const Color(0xFF1A2035), width: 1),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Orders by Category',
            style: TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 24),
          Expanded(
            child: Row(
              children: [
                Expanded(
                  flex: 3,
                  child: PieChart(
                    PieChartData(
                      sectionsSpace: 2,
                      centerSpaceRadius: 50,
                      sections: sections,
                    ),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  flex: 2,
                  child: SingleChildScrollView(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: legendItems.isEmpty
                          ? [
                              const Text(
                                'No sales yet',
                                style: TextStyle(color: Colors.white54),
                              ),
                            ]
                          : legendItems,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLegendItem(Color color, String label) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              label,
              style: const TextStyle(color: Colors.white70, fontSize: 11),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRecentOrdersTab() {
    return Column(
      children: [
        // Filter Bar
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          child: Row(
            children: [
              _buildFilterButton('Today', 1),
              const SizedBox(width: 8),
              _buildFilterButton('7 Days', 7),
              const SizedBox(width: 8),
              _buildFilterButton('30 Days', 30),
            ],
          ),
        ),
        // Content area
        Expanded(
          child: _isLoadingOrders
              ? const Center(child: CircularProgressIndicator())
              : _recentOrders.isEmpty
              ? const Center(
                  child: Text(
                    'No recent orders',
                    style: TextStyle(color: Colors.white54),
                  ),
                )
              : LayoutBuilder(
                  builder: (context, constraints) {
                    if (constraints.maxWidth > 1100) {
                      return _buildDesktopOrdersTable();
                    }
                    return _buildMobileOrdersList();
                  },
                ),
        ),
        // Pagination
        if (!_isLoadingOrders && _recentOrders.isNotEmpty)
          _buildPaginationControls(),
      ],
    );
  }

  Widget _buildFilterButton(String label, int days) {
    final isActive = _ordersDaysFilter == days;
    return Material(
      color: Colors.transparent,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        mouseCursor: SystemMouseCursors.click,
        hoverColor: const Color(0xFF6366F1).withOpacity(0.10),
        splashColor: const Color(0xFF6366F1).withOpacity(0.18),
        onTap: () {
          setState(() {
            _ordersDaysFilter = days;
            _ordersCurrentPage = 0;
            _expandedOrderIds.clear();
          });
          _fetchRecentOrders();
        },
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            color: isActive ? const Color(0xFF13183A) : Colors.transparent,
            border: Border.all(
              color: isActive
                  ? const Color(0xFF6366F1)
                  : const Color(0xFF1A2035),
            ),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Text(
            label,
            style: TextStyle(
              color: isActive ? const Color(0xFF818CF8) : Colors.white70,
              fontSize: 13,
              fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPaginationControls() {
    final int totalPages = (_recentOrders.length / _ordersPerPage).ceil();
    if (totalPages <= 1) return const SizedBox();

    return Container(
      padding: const EdgeInsets.all(16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          IconButton(
            icon: const Icon(Icons.chevron_left, color: Colors.white70),
            onPressed: _ordersCurrentPage > 0
                ? () => setState(() => _ordersCurrentPage--)
                : null,
          ),
          Text(
            'Page ${_ordersCurrentPage + 1} of $totalPages',
            style: const TextStyle(color: Colors.white, fontSize: 13),
          ),
          IconButton(
            icon: const Icon(Icons.chevron_right, color: Colors.white70),
            onPressed: _ordersCurrentPage < totalPages - 1
                ? () => setState(() => _ordersCurrentPage++)
                : null,
          ),
        ],
      ),
    );
  }

  List<dynamic> get _paginatedOrders {
    final int startIndex = _ordersCurrentPage * _ordersPerPage;
    final int endIndex = startIndex + _ordersPerPage;
    if (startIndex >= _recentOrders.length) return [];
    return _recentOrders.sublist(
      startIndex,
      endIndex > _recentOrders.length ? _recentOrders.length : endIndex,
    );
  }

  Widget _buildDesktopOrdersTable() {
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Container(
        width: double.infinity,
        decoration: BoxDecoration(
          color: const Color(0xFF0D111C),
          border: Border.all(color: const Color(0xFF1A2035)),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Theme(
          data: Theme.of(
            context,
          ).copyWith(dividerColor: const Color(0xFF1A2035)),
          child: DataTable(
            dataRowMaxHeight: double.infinity,
            dataRowMinHeight: 60,
            headingTextStyle: const TextStyle(
              color: Color(0xFF3D4A6B),
              fontSize: 11,
              fontWeight: FontWeight.bold,
              letterSpacing: 0.6,
            ),
            columns: const [
              DataColumn(label: Text('ORDER ID')),
              DataColumn(label: Text('CUSTOMER')),
              DataColumn(label: Text('ITEMS')),
              DataColumn(label: Text('AMOUNT')),
              DataColumn(label: Text('STATUS')),
              DataColumn(label: Text('REVIEWS')),
            ],
            rows: _paginatedOrders.map((o) {
              final items = (o['items'] as List).join(', ');
              final isExpanded = _expandedOrderIds.contains(o['order_id']);

              return DataRow(
                cells: [
                  DataCell(
                    Text(
                      '#${o['order_id']}',
                      style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 13,
                      ),
                    ),
                  ),
                  DataCell(
                    Text(
                      o['customer_name']?.toString() ?? 'Guest',
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w500,
                        fontSize: 13,
                      ),
                    ),
                  ),
                  DataCell(
                    InkWell(
                      onTap: () {
                        setState(() {
                          if (isExpanded) {
                            _expandedOrderIds.remove(o['order_id']);
                          } else {
                            _expandedOrderIds.add(o['order_id']);
                          }
                        });
                      },
                      child: Container(
                        constraints: const BoxConstraints(maxWidth: 250),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(
                              items,
                              maxLines: isExpanded ? null : 1,
                              overflow: isExpanded
                                  ? null
                                  : TextOverflow.ellipsis,
                              style: const TextStyle(
                                color: Colors.white70,
                                fontSize: 13,
                              ),
                            ),
                            if (!isExpanded && items.length > 30)
                              const Text(
                                'Tap to expand',
                                style: TextStyle(
                                  color: Colors.blueAccent,
                                  fontSize: 10,
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  DataCell(
                    Text(
                      'Rs ${o['total']}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                        fontSize: 13,
                      ),
                    ),
                  ),
                  DataCell(
                    _buildStatusBadge(o['status']?.toString() ?? 'unknown'),
                  ),
                  DataCell(
                    o['review_rating'] != null
                        ? InkWell(
                            onTap: () {
                              setState(() {
                                if (isExpanded) {
                                  _expandedOrderIds.remove(o['order_id']);
                                } else {
                                  _expandedOrderIds.add(o['order_id']);
                                }
                              });
                            },
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Row(
                                  children: List.generate(
                                    5,
                                    (index) => Icon(
                                      index < (o['review_rating'] as int)
                                          ? Icons.star
                                          : Icons.star_border,
                                      color: Colors.amber,
                                      size: 14,
                                    ),
                                  ),
                                ),
                                if (isExpanded && o['review_text'] != null)
                                  Padding(
                                    padding: const EdgeInsets.only(top: 4.0),
                                    child: Text(
                                      o['review_text'],
                                      style: const TextStyle(
                                        color: Colors.white60,
                                        fontSize: 11,
                                        fontStyle: FontStyle.italic,
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                          )
                        : const Text(
                            '-',
                            style: TextStyle(color: Colors.white24),
                          ),
                  ),
                ],
              );
            }).toList(),
          ),
        ),
      ),
    );
  }

  Widget _buildMobileOrdersList() {
    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      itemCount: _paginatedOrders.length,
      itemBuilder: (context, index) {
        final o = _paginatedOrders[index];
        final items = (o['items'] as List).join(', ');
        final isExpanded = _expandedOrderIds.contains(o['order_id']);

        return Card(
          color: const Color(0xFF0D111C),
          margin: const EdgeInsets.only(bottom: 12),
          shape: RoundedRectangleBorder(
            side: const BorderSide(color: Color(0xFF1A2035)),
            borderRadius: BorderRadius.circular(10),
          ),
          child: InkWell(
            onTap: () {
              setState(() {
                if (isExpanded) {
                  _expandedOrderIds.remove(o['order_id']);
                } else {
                  _expandedOrderIds.add(o['order_id']);
                }
              });
            },
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        o['customer_name']?.toString() ?? 'Guest',
                        style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                          fontSize: 15,
                        ),
                      ),
                      Text(
                        'Rs ${o['total']}',
                        style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                          fontSize: 15,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    items,
                    maxLines: isExpanded ? null : 1,
                    overflow: isExpanded ? null : TextOverflow.ellipsis,
                    style: const TextStyle(color: Colors.white54, fontSize: 13),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      _buildStatusBadge(o['status']?.toString() ?? 'unknown'),
                      if (o['review_rating'] != null)
                        Row(
                          children: List.generate(
                            5,
                            (ri) => Icon(
                              ri < (o['review_rating'] as int)
                                  ? Icons.star
                                  : Icons.star_border,
                              color: Colors.amber,
                              size: 14,
                            ),
                          ),
                        ),
                    ],
                  ),
                  if (isExpanded && o['review_text'] != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 12.0),
                      child: Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.02),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          '"${o['review_text']}"',
                          style: const TextStyle(
                            color: Colors.white60,
                            fontSize: 12,
                            fontStyle: FontStyle.italic,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildStatusBadge(String status) {
    Color bg;
    Color text;
    final lower = status.toLowerCase();

    if (lower == 'completed') {
      bg = const Color(0xFF0A1A12);
      text = const Color(0xFF34D399);
    } else if (lower == 'preparing' || lower == 'in_kitchen') {
      bg = const Color(0xFF2D1F0E);
      text = Colors.amber;
    } else if (lower == 'cancelled') {
      bg = const Color(0xFF1A080A);
      text = const Color(0xFFF87171);
    } else {
      // created, confirmed, ready
      bg = const Color(0xFF13183A);
      text = const Color(0xFF818CF8);
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        status.toUpperCase(),
        style: TextStyle(
          color: text,
          fontSize: 10,
          fontWeight: FontWeight.bold,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}

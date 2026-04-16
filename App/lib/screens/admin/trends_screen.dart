import 'dart:async';

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:khaadim/services/api_client.dart';

class TrendsScreen extends StatefulWidget {
  const TrendsScreen({super.key});

  @override
  State<TrendsScreen> createState() => _TrendsScreenState();
}

class _TrendsScreenState extends State<TrendsScreen> {
  bool _isLoading = true;
  int _selectedPeriod = 30;
  Timer? _autoRefreshTimer;

  List<Map<String, dynamic>> _topItems = [];
  List<Map<String, dynamic>> _lowItems = [];
  List<double> _hourlyAvgOrders = List<double>.filled(24, 0.0);

  // Track hover state for subtle desktop/web row highlight.
  final Set<String> _hoveredRows = <String>{};
  final Set<String> _expandedNameRows = <String>{};

  @override
  void initState() {
    super.initState();
    _fetchTrendsData();
    _startAutoRefresh();
  }

  @override
  void dispose() {
    _autoRefreshTimer?.cancel();
    super.dispose();
  }

  void _startAutoRefresh() {
    _autoRefreshTimer?.cancel();
    _autoRefreshTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      if (!mounted || _isLoading) return;
      _fetchTrendsData(showLoader: false);
    });
  }

  Future<void> _fetchTrendsData({bool showLoader = true}) async {
    if (showLoader) {
      setState(() => _isLoading = true);
    }
    try {
      final endpoint = '/admin/trends?period=$_selectedPeriod';
      final data = await ApiClient.getJson(endpoint, auth: true);

      final topRaw = (data['top_items'] as List<dynamic>? ?? []);
      final lowRaw = (data['low_items'] as List<dynamic>? ?? []);
      final hourlyRaw = (data['hourly_data'] as List<dynamic>? ?? []);

      final topItems = topRaw
          .map((e) => Map<String, dynamic>.from(e as Map))
          .take(5)
          .toList();
      final lowItems = lowRaw
          .map((e) => Map<String, dynamic>.from(e as Map))
          .take(5)
          .toList();

      final hourlyFilled = List<double>.filled(24, 0.0);
      for (final row in hourlyRaw) {
        final mapped = Map<String, dynamic>.from(row as Map);
        final hour = (mapped['hour'] as num?)?.toInt() ?? -1;
        final avg = (mapped['avg_orders'] as num?)?.toDouble() ?? 0.0;
        if (hour >= 0 && hour < 24) {
          hourlyFilled[hour] = avg;
        }
      }

      if (mounted) {
        setState(() {
          _topItems = topItems;
          _lowItems = lowItems;
          _hourlyAvgOrders = hourlyFilled;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        if (showLoader) {
          setState(() => _isLoading = false);
        }
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to load trends data: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isDesktop = constraints.maxWidth > 1100;

        return Column(
          children: [
            _buildFilterBar(isDesktop),
            Expanded(
              child: _isLoading
                  ? const Center(child: CircularProgressIndicator())
                  : SingleChildScrollView(
                      padding: const EdgeInsets.all(24),
                      child: isDesktop
                          ? _buildDesktopContent()
                          : _buildMobileContent(),
                    ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildFilterBar(bool isDesktop) {
    return Container(
      color: const Color(0xFF0D111C),
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
      child: isDesktop
          ? Row(
              mainAxisAlignment: MainAxisAlignment.start,
              children: [_buildPeriodToggle()],
            )
          : SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(children: [_buildPeriodToggle()]),
            ),
    );
  }

  Widget _buildPeriodToggle() {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF13183A),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF1A2035)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [7, 30, 90].map((days) {
          final isSelected = _selectedPeriod == days;
          return Material(
            color: Colors.transparent,
            borderRadius: BorderRadius.circular(8),
            child: InkWell(
              borderRadius: BorderRadius.circular(8),
              mouseCursor: SystemMouseCursors.click,
              hoverColor: const Color(0xFF6366F1).withOpacity(0.10),
              splashColor: const Color(0xFF6366F1).withOpacity(0.18),
              onTap: () {
                if (!isSelected) {
                  setState(() => _selectedPeriod = days);
                  _fetchTrendsData();
                }
              },
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: isSelected
                      ? const Color(0xFF6366F1).withOpacity(0.2)
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  '${days}D',
                  style: TextStyle(
                    color: isSelected
                        ? const Color(0xFF818CF8)
                        : Colors.white70,
                    fontWeight: isSelected
                        ? FontWeight.w600
                        : FontWeight.normal,
                    fontSize: 13,
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildDesktopContent() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: _buildItemsTable(
                title: 'Top Selling Items',
                items: _topItems,
                rankColor: const Color(0xFF6366F1),
                rowPrefix: 'top',
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: _buildItemsTable(
                title: 'Low Selling Items',
                items: _lowItems,
                rankColor: const Color(0xFFF43F5E),
                rowPrefix: 'low',
              ),
            ),
          ],
        ),
        const SizedBox(height: 24),
        _buildHourlyChartCard(height: 360),
      ],
    );
  }

  Widget _buildMobileContent() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildItemsTable(
          title: 'Top Selling Items',
          items: _topItems,
          rankColor: const Color(0xFF6366F1),
          rowPrefix: 'top',
          allowNameExpand: true,
        ),
        const SizedBox(height: 16),
        _buildItemsTable(
          title: 'Low Selling Items',
          items: _lowItems,
          rankColor: const Color(0xFFF43F5E),
          rowPrefix: 'low',
          allowNameExpand: true,
        ),
        const SizedBox(height: 16),
        _buildHourlyChartCard(height: 300),
      ],
    );
  }

  Widget _buildItemsTable({
    required String title,
    required List<Map<String, dynamic>> items,
    required Color rankColor,
    required String rowPrefix,
    bool allowNameExpand = false,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0D111C),
        border: Border.all(color: const Color(0xFF1A2035)),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 12),
          _buildTableHeader(),
          const SizedBox(height: 6),
          if (items.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 18),
              child: Center(
                child: Text(
                  'No data for this period',
                  style: TextStyle(color: Colors.white54),
                ),
              ),
            )
          else
            ...List.generate(items.length, (index) {
              final row = items[index];
              final rowId = '$rowPrefix-$index';
              final isHovered = _hoveredRows.contains(rowId);

              final rankNum = index + 1;
              final rankText = '#${rankNum.toString().padLeft(2, '0')}';
              final itemName = (row['name'] ?? '').toString();
              final isNameExpanded = _expandedNameRows.contains(rowId);
              final units = ((row['units_sold'] as num?)?.toInt() ?? 0)
                  .toString();
              final revenue = ((row['revenue'] as num?)?.toDouble() ?? 0.0);

              return MouseRegion(
                onEnter: (_) => setState(() => _hoveredRows.add(rowId)),
                onExit: (_) => setState(() => _hoveredRows.remove(rowId)),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 120),
                  margin: const EdgeInsets.only(bottom: 4),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 10,
                  ),
                  decoration: BoxDecoration(
                    color: isHovered
                        ? Colors.white.withOpacity(0.04)
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 56,
                        child: Text(
                          rankText,
                          style: TextStyle(
                            color: rankColor,
                            fontWeight: FontWeight.w700,
                            fontSize: 13,
                          ),
                        ),
                      ),
                      Expanded(
                        flex: 3,
                        child: GestureDetector(
                          onTap: allowNameExpand
                              ? () {
                                  setState(() {
                                    if (isNameExpanded) {
                                      _expandedNameRows.remove(rowId);
                                    } else {
                                      _expandedNameRows.add(rowId);
                                    }
                                  });
                                }
                              : null,
                          child: Text(
                            itemName,
                            maxLines: allowNameExpand && isNameExpanded
                                ? null
                                : 1,
                            overflow: allowNameExpand && isNameExpanded
                                ? TextOverflow.visible
                                : TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 13,
                            ),
                          ),
                        ),
                      ),
                      SizedBox(
                        width: 68,
                        child: Text(
                          units,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            color: Colors.white70,
                            fontSize: 13,
                          ),
                        ),
                      ),
                      SizedBox(
                        width: 96,
                        child: Text(
                          'Rs ${revenue.toStringAsFixed(0)}',
                          textAlign: TextAlign.right,
                          style: const TextStyle(
                            color: Color(0xFF818CF8),
                            fontWeight: FontWeight.w600,
                            fontSize: 13,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            }),
        ],
      ),
    );
  }

  Widget _buildTableHeader() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.02),
        borderRadius: BorderRadius.circular(8),
      ),
      child: const Row(
        children: [
          SizedBox(
            width: 56,
            child: Text(
              'Rank',
              style: TextStyle(
                color: Colors.white54,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          Expanded(
            flex: 3,
            child: Text(
              'Item Name',
              style: TextStyle(
                color: Colors.white54,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          SizedBox(
            width: 68,
            child: Text(
              'Units',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white54,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          SizedBox(
            width: 96,
            child: Text(
              'Revenue',
              textAlign: TextAlign.right,
              style: TextStyle(
                color: Colors.white54,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHourlyChartCard({required double height}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF0D111C),
        border: Border.all(color: const Color(0xFF1A2035)),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Order Volume by Hour of Day',
            style: TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 20),
          SizedBox(
            height: height,
            child: BarChart(
              BarChartData(
                alignment: BarChartAlignment.spaceAround,
                maxY: _chartMaxY(),
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  getDrawingHorizontalLine: (_) =>
                      const FlLine(color: Color(0xFF1A2035), strokeWidth: 1),
                ),
                borderData: FlBorderData(
                  show: true,
                  border: const Border(
                    left: BorderSide(color: Color(0xFF1A2035), width: 1),
                    bottom: BorderSide(color: Color(0xFF1A2035), width: 1),
                  ),
                ),
                titlesData: FlTitlesData(
                  topTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  rightTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 34,
                      getTitlesWidget: (value, meta) => Text(
                        value.toInt().toString(),
                        style: const TextStyle(
                          color: Colors.white54,
                          fontSize: 10,
                        ),
                      ),
                    ),
                  ),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 24,
                      getTitlesWidget: (value, meta) {
                        final int hour = value.toInt();
                        if (hour < 0 || hour > 23) {
                          return const SizedBox.shrink();
                        }
                        // Keep x-axis readable on smaller widths.
                        if (MediaQuery.of(context).size.width <= 500 &&
                            hour % 3 != 0) {
                          return const SizedBox.shrink();
                        }
                        return SideTitleWidget(
                          meta: meta,
                          child: Text(
                            '$hour:00',
                            style: const TextStyle(
                              color: Colors.white54,
                              fontSize: 9,
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                ),
                barTouchData: BarTouchData(
                  enabled: true,
                  touchTooltipData: BarTouchTooltipData(
                    getTooltipColor: (_) => const Color(0xFF1E293B),
                    getTooltipItem: (group, groupIndex, rod, rodIndex) {
                      return BarTooltipItem(
                        '${group.x}:00\n${rod.toY.toStringAsFixed(2)} avg orders',
                        const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                          fontSize: 11,
                        ),
                      );
                    },
                  ),
                ),
                barGroups: List.generate(24, (hour) {
                  final value = _hourlyAvgOrders[hour];
                  return BarChartGroupData(
                    x: hour,
                    barRods: [
                      BarChartRodData(
                        toY: value,
                        width: 9,
                        color: _barColorForValue(value),
                        borderRadius: const BorderRadius.vertical(
                          top: Radius.circular(3),
                        ),
                      ),
                    ],
                  );
                }),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Color _barColorForValue(double value) {
    if (value > 80) return const Color(0xFF6366F1);
    if (value > 50) return const Color(0xFF6366F1).withOpacity(0.65);
    if (value > 25) return const Color(0xFF6366F1).withOpacity(0.35);
    return const Color(0xFF6366F1).withOpacity(0.15);
  }

  double _chartMaxY() {
    final maxVal = _hourlyAvgOrders.fold<double>(0.0, (p, v) => v > p ? v : p);
    if (maxVal <= 0) return 5;
    return (maxVal * 1.2).ceilToDouble();
  }
}

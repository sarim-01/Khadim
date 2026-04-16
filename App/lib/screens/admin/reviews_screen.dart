import 'dart:async';

import 'package:flutter/material.dart';
import 'package:khaadim/services/api_client.dart';

class ReviewsScreen extends StatefulWidget {
  const ReviewsScreen({super.key});

  @override
  State<ReviewsScreen> createState() => _ReviewsScreenState();
}

class _ReviewsScreenState extends State<ReviewsScreen>
    with SingleTickerProviderStateMixin {
  bool _isLoading = true;
  String _selectedCategory = 'all';
  String _searchQuery = '';
  Timer? _autoRefreshTimer;

  List<String> _categories = const ['all'];
  List<Map<String, dynamic>> _items = [];

  late final AnimationController _shimmerController;

  @override
  void initState() {
    super.initState();
    _shimmerController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);
    _fetchReviews();
    _startAutoRefresh();
  }

  @override
  void dispose() {
    _autoRefreshTimer?.cancel();
    _shimmerController.dispose();
    super.dispose();
  }

  void _startAutoRefresh() {
    _autoRefreshTimer?.cancel();
    _autoRefreshTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      if (!mounted || _isLoading) return;
      _fetchReviews(showLoader: false, showError: false);
    });
  }

  Future<void> _fetchReviews({
    bool showLoader = true,
    bool showError = true,
  }) async {
    if (showLoader) {
      setState(() => _isLoading = true);
    }
    try {
      final endpoint = '/admin/reviews?category=$_selectedCategory';
      final data = await ApiClient.getJson(endpoint, auth: true);

      final rawCategories = (data['categories'] as List<dynamic>? ?? []);
      final rawItems = (data['items'] as List<dynamic>? ?? []);

      final categories = {
        'all',
        ...rawCategories
            .map((e) => e.toString())
            .where((e) => e.trim().isNotEmpty),
      }.toList();

      final parsed = rawItems
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();

      if (mounted) {
        setState(() {
          _categories = categories;
          _items = parsed;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        if (showLoader) {
          setState(() => _isLoading = false);
        }
        if (showError) {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text('Failed to load reviews: $e')));
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final bool isDesktop = constraints.maxWidth > 1100;
        final bool useTwoColumns = constraints.maxWidth > 1200;

        return Column(
          children: [
            _buildFilterBar(isDesktop),
            Expanded(
              child: _isLoading
                  ? _buildLoadingState(useTwoColumns)
                  : _buildBody(useTwoColumns),
            ),
          ],
        );
      },
    );
  }

  Widget _buildFilterBar(bool isDesktop) {
    final categoryFilter = _buildCategoryDropdown();
    final searchField = SizedBox(
      width: isDesktop ? 300 : double.infinity,
      child: TextField(
        onChanged: (value) => setState(() => _searchQuery = value.trim()),
        style: const TextStyle(color: Colors.white, fontSize: 13),
        decoration: InputDecoration(
          hintText: 'Search item name',
          hintStyle: const TextStyle(color: Colors.white38, fontSize: 13),
          prefixIcon: const Icon(Icons.search, color: Colors.white54, size: 18),
          filled: true,
          fillColor: const Color(0xFF13183A),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 10,
            vertical: 8,
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide: const BorderSide(color: Color(0xFF1A2035)),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide: const BorderSide(color: Color(0xFF6366F1)),
          ),
        ),
      ),
    );

    return Container(
      color: const Color(0xFF0D111C),
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
      child: isDesktop
          ? Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [categoryFilter, searchField],
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                categoryFilter,
                const SizedBox(height: 12),
                searchField,
              ],
            ),
    );
  }

  Widget _buildCategoryDropdown() {
    return Container(
      height: 38,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF13183A),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF1A2035)),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: _selectedCategory,
          dropdownColor: const Color(0xFF13183A),
          icon: const Icon(Icons.keyboard_arrow_down, color: Colors.white54),
          style: const TextStyle(color: Colors.white, fontSize: 13),
          items: _categories
              .map(
                (cat) => DropdownMenuItem<String>(
                  value: cat,
                  child: Text(_categoryLabel(cat)),
                ),
              )
              .toList(),
          onChanged: (value) {
            if (value != null && value != _selectedCategory) {
              setState(() => _selectedCategory = value);
              _fetchReviews();
            }
          },
        ),
      ),
    );
  }

  String _categoryLabel(String category) {
    final lower = category.toLowerCase();
    if (lower == 'all') return 'All Categories';
    if (lower == 'desi') return 'Pakistani';
    return category;
  }

  Widget _buildLoadingState(bool useTwoColumns) {
    return AnimatedBuilder(
      animation: _shimmerController,
      builder: (context, child) {
        final pulse = 0.12 + (0.12 * _shimmerController.value);
        final cards = List.generate(3, (_) => _buildSkeletonCard(pulse));

        return SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Center(
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: useTwoColumns ? 1160 : 860),
              child: useTwoColumns
                  ? LayoutBuilder(
                      builder: (context, constraints) {
                        final width = (constraints.maxWidth - 16) / 2;
                        return Wrap(
                          spacing: 16,
                          runSpacing: 16,
                          children: cards
                              .map(
                                (card) => SizedBox(width: width, child: card),
                              )
                              .toList(),
                        );
                      },
                    )
                  : Column(
                      children: cards
                          .map(
                            (card) => Padding(
                              padding: const EdgeInsets.only(bottom: 14),
                              child: card,
                            ),
                          )
                          .toList(),
                    ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildSkeletonCard(double pulse) {
    final color = Colors.white.withOpacity(pulse);

    Widget line(double width, double height) {
      return Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(4),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0D111C),
        border: Border.all(color: const Color(0xFF1A2035)),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          line(180, 14),
          const SizedBox(height: 12),
          line(140, 10),
          const SizedBox(height: 8),
          line(double.infinity, 10),
          const SizedBox(height: 6),
          line(double.infinity, 10),
        ],
      ),
    );
  }

  Widget _buildBody(bool useTwoColumns) {
    final filtered = _filteredItems();
    if (filtered.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: 24),
          child: Text(
            'No reviews yet. Reviews will appear here once customers start rating items.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.white54, fontSize: 15),
          ),
        ),
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Center(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: useTwoColumns ? 1160 : 860),
          child: useTwoColumns
              ? LayoutBuilder(
                  builder: (context, constraints) {
                    final itemWidth = (constraints.maxWidth - 16) / 2;
                    return Wrap(
                      spacing: 16,
                      runSpacing: 16,
                      children: filtered
                          .map(
                            (item) => SizedBox(
                              width: itemWidth,
                              child: _buildItemCard(item),
                            ),
                          )
                          .toList(),
                    );
                  },
                )
              : Column(
                  children: filtered
                      .map(
                        (item) => Padding(
                          padding: const EdgeInsets.only(bottom: 14),
                          child: _buildItemCard(item),
                        ),
                      )
                      .toList(),
                ),
        ),
      ),
    );
  }

  List<Map<String, dynamic>> _filteredItems() {
    if (_searchQuery.isEmpty) return _items;
    final q = _searchQuery.toLowerCase();
    return _items.where((item) {
      final name = (item['item_name'] ?? '').toString().toLowerCase();
      return name.contains(q);
    }).toList();
  }

  Widget _buildItemCard(Map<String, dynamic> item) {
    final itemName = (item['item_name'] ?? 'Unknown Item').toString();
    final category = (item['category'] ?? 'unknown').toString();
    final itemType = (item['item_type'] ?? 'menu_item').toString();
    final avgRating = (item['avg_rating'] as num?)?.toDouble() ?? 0.0;
    final totalReviews = (item['total_reviews'] as num?)?.toInt() ?? 0;
    final isLowRated = totalReviews > 0 && avgRating < 3.0;

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF0D111C),
        borderRadius: BorderRadius.circular(10),
        border: Border(
          left: BorderSide(
            color: isLowRated
                ? const Color(0xFFF43F5E)
                : const Color(0xFF1A2035),
            width: isLowRated ? 3 : 1,
          ),
          top: const BorderSide(color: Color(0xFF1A2035), width: 1),
          right: const BorderSide(color: Color(0xFF1A2035), width: 1),
          bottom: const BorderSide(color: Color(0xFF1A2035), width: 1),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 8,
              runSpacing: 6,
              children: [
                Text(
                  itemName,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 3,
                  ),
                  decoration: BoxDecoration(
                    color: const Color(0xFF13183A),
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(color: const Color(0xFF1A2035)),
                  ),
                  child: Text(
                    _categoryLabel(category),
                    style: const TextStyle(
                      color: Colors.white60,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                if (itemType == 'deal')
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: const Color(0xFF0F172A),
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(color: const Color(0xFF1A2035)),
                    ),
                    child: const Text(
                      'Deal',
                      style: TextStyle(
                        color: Colors.white60,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 8,
              runSpacing: 8,
              children: [
                _buildStarRow(avgRating),
                Text(
                  avgRating.toStringAsFixed(1),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                Text(
                  '($totalReviews reviews)',
                  style: const TextStyle(color: Colors.white54, fontSize: 12),
                ),
                const Text(
                  'All-time rating',
                  style: TextStyle(color: Colors.white38, fontSize: 11),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStarRow(double value) {
    final stars = List<Widget>.generate(5, (i) {
      IconData icon;
      if (value >= i + 1) {
        icon = Icons.star;
      } else if (value >= i + 0.5) {
        icon = Icons.star_half;
      } else {
        icon = Icons.star_border;
      }

      return Icon(icon, size: 15, color: const Color(0xFFF59E0B));
    });

    return Row(mainAxisSize: MainAxisSize.min, children: stars);
  }
}

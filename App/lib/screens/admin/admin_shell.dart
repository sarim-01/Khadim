import 'package:flutter/material.dart';
import '../../services/auth_service.dart';
import '../../services/api_client.dart';
import '../../services/token_storage.dart';
import 'overview_screen.dart';
import 'revenue_screen.dart';
import 'trends_screen.dart';
import 'reviews_screen.dart';
import 'ai_screen.dart';
import 'restaurant_management_screen.dart';

class AdminShell extends StatefulWidget {
  const AdminShell({super.key});

  @override
  State<AdminShell> createState() => _AdminShellState();
}

class _AdminShellState extends State<AdminShell> {
  int _currentIndex = 0;
  String _adminName = 'Admin';
  bool _isLoadingName = true;
  bool _checkingAccess = true;
  String? _accessError;

  final Color _bgDark = const Color(0xFF07090F);
  final Color _bgSidebar = const Color(0xFF0D111C);
  final Color _accent = const Color(0xFF6366F1);

  final List<Widget> _screens = const [
    OverviewScreen(),
    RevenueScreen(),
    TrendsScreen(),
    ReviewsScreen(),
    Center(
      child: Text(
        'Agent Performance Placeholder',
        style: TextStyle(color: Colors.white, fontSize: 24),
      ),
    ),
    AIScreen(),
    RestaurantManagementScreen(),
  ];

  final List<Map<String, dynamic>> _navItems = [
    {'label': 'Overview', 'icon': Icons.dashboard_outlined},
    {'label': 'Revenue', 'icon': Icons.attach_money},
    {'label': 'Trends', 'icon': Icons.trending_up},
    {'label': 'Reviews', 'icon': Icons.comment_outlined},
    {'label': 'Agent Performance', 'icon': Icons.smart_toy_outlined},
    {'label': 'AI Suggestions', 'icon': Icons.lightbulb_outline},
    {'label': 'Restaurant', 'icon': Icons.table_restaurant},
  ];

  @override
  void initState() {
    super.initState();
    _validateAdminAccess();
  }

  // ── FIXED: routes to admin login, not customer LoginScreen ──
  void _goToLogin() {
    if (!mounted) return;
    Navigator.of(context).pushReplacementNamed('/admin-login');
  }

  void _goToMain() {
    if (!mounted) return;
    Navigator.of(context).pushReplacementNamed('/admin-login');
  }

  // ── UNCHANGED: original logic preserved exactly ─────────────
  Future<void> _validateAdminAccess() async {
    try {
      final data = await AuthService.me().timeout(const Duration(seconds: 8));
      final user = data['user'] ?? data;
      final email = (user['email'] ?? '').toString().toLowerCase();

      if (!mounted) return;

      if (email != 'admin@gmail.com') {
        _goToMain();
        return;
      }

      setState(() {
        _adminName = user['full_name'] ?? 'Admin';
        _isLoadingName = false;
        _checkingAccess = false;
        _accessError = null;
      });
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          _checkingAccess = false;
          _accessError = e.message;
        });
      }
      if (e.isUnauthorized) {
        await TokenStorage.clearToken();
      }
      _goToLogin();
    } catch (_) {
      if (mounted) {
        setState(() {
          _checkingAccess = false;
          _accessError = 'Unable to verify admin access';
        });
      }
      await TokenStorage.clearToken();
      _goToLogin();
    }
  }

  Future<void> _handleSignOut() async {
    await TokenStorage.clearToken();
    _goToLogin();
  }

  @override
  Widget build(BuildContext context) {
    if (_checkingAccess) {
      return const Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 12),
              Text('Checking admin access...'),
            ],
          ),
        ),
      );
    }

    if (_accessError != null) {
      return Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(_accessError!, textAlign: TextAlign.center),
                const SizedBox(height: 12),
                ElevatedButton(
                  onPressed: () {
                    setState(() {
                      _checkingAccess = true;
                      _accessError = null;
                    });
                    _validateAdminAccess();
                  },
                  child: const Text('Retry'),
                ),
                const SizedBox(height: 8),
                TextButton(
                  onPressed: _goToLogin,
                  child: const Text('Back to Login'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Scaffold(
      backgroundColor: _bgDark,
      body: LayoutBuilder(
        builder: (context, constraints) {
          if (constraints.maxWidth > 1100) {
            return _buildDesktopLayout();
          } else {
            return _buildMobileLayout();
          }
        },
      ),
    );
  }

  Widget _buildDesktopLayout() {
    return Row(
      children: [
        Container(
          width: 220,
          color: _bgSidebar,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 32, 24, 32),
                child: Text(
                  'Khadim',
                  style: TextStyle(
                    color: _accent,
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 1.2,
                  ),
                ),
              ),
              Expanded(
                child: ListView(
                  children: [
                    _buildNavLabel('Main'),
                    _buildNavItem(0),
                    _buildNavItem(1),
                    _buildNavItem(2),
                    _buildNavLabel('Insights'),
                    _buildNavItem(3),
                    _buildNavItem(4),
                    _buildNavItem(5),
                    _buildNavItem(6),
                  ],
                ),
              ),
              Divider(color: Colors.white10, height: 1),
              Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        CircleAvatar(
                          radius: 16,
                          backgroundColor: _accent.withOpacity(0.2),
                          child: Icon(Icons.person, size: 18, color: _accent),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _isLoadingName
                              ? const SizedBox(
                                  height: 12,
                                  width: 12,
                                  child:
                                      CircularProgressIndicator(strokeWidth: 2),
                                )
                              : Text(
                                  _adminName,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 14,
                                    fontWeight: FontWeight.w500,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        icon: const Icon(Icons.logout,
                            size: 16, color: Colors.white70),
                        label: const Text('Sign out',
                            style:
                                TextStyle(color: Colors.white70, fontSize: 13)),
                        style: OutlinedButton.styleFrom(
                          side: const BorderSide(color: Colors.white24),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8)),
                        ),
                        onPressed: _handleSignOut,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: Column(
            children: [
              _buildTopBar(),
              Expanded(
                child: IndexedStack(index: _currentIndex, children: _screens),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildTopBar() {
    return Container(
      height: 64,
      padding: const EdgeInsets.symmetric(horizontal: 28),
      decoration: BoxDecoration(
        color: _bgSidebar,
        border: const Border(bottom: BorderSide(color: Color(0xFF1A2035))),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                _navItems[_currentIndex]['label'] as String,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: const Color(0xFF0A1A12),
              border: Border.all(color: const Color(0xFF14532D)),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              children: [
                Container(
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(
                    color: Colors.greenAccent,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 6),
                const Text('Live',
                    style: TextStyle(
                      color: Colors.greenAccent,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.5,
                    )),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNavLabel(String text) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(22, 16, 22, 6),
      child: Text(
        text.toUpperCase(),
        style: const TextStyle(
          color: Color(0xFF3D4A6B),
          fontSize: 11,
          letterSpacing: 0.8,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  Widget _buildNavItem(int index) {
    final item = _navItems[index];
    final isSelected = _currentIndex == index;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
      decoration: BoxDecoration(
        color: isSelected ? _accent.withOpacity(0.15) : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        child: ListTile(
          leading: Icon(item['icon'] as IconData,
              color: isSelected ? _accent : Colors.white70, size: 20),
          title: Text(item['label'] as String,
              style: TextStyle(
                color: isSelected ? _accent : Colors.white70,
                fontSize: 13,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
              )),
          onTap: () => setState(() => _currentIndex = index),
          mouseCursor: SystemMouseCursors.click,
          hoverColor: _accent.withOpacity(0.10),
          dense: true,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      ),
    );
  }

  Widget _buildMobileLayout() {
    return Scaffold(
      backgroundColor: _bgDark,
      appBar: AppBar(
        title: const Text('Khadim Admin',
            style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: _bgSidebar,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: _handleSignOut,
            tooltip: 'Sign Out',
          ),
        ],
      ),
      body: IndexedStack(index: _currentIndex, children: _screens),
      bottomNavigationBar: Theme(
        data: Theme.of(context).copyWith(canvasColor: _bgSidebar),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          onTap: (index) => setState(() => _currentIndex = index),
          type: BottomNavigationBarType.fixed,
          backgroundColor: _bgSidebar,
          selectedItemColor: _accent,
          unselectedItemColor: Colors.white54,
          selectedFontSize: 11,
          unselectedFontSize: 11,
          items: _navItems.map((item) {
            return BottomNavigationBarItem(
              icon: Icon(item['icon'] as IconData, size: 22),
              label: (item['label'] as String).split(' ').first,
            );
          }).toList(),
        ),
      ),
    );
  }
}

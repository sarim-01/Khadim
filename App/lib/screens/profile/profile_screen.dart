import 'package:flutter/material.dart';
import 'personal_info_screen.dart';
import 'package:khaadim/screens/orders/order_history_screen.dart';
import 'package:khaadim/screens/profile/settings_screen.dart';
import 'package:khaadim/screens/support/favorites_screen.dart';
import 'package:khaadim/services/auth_service.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  String _fullName = '';
  String _email = '';
  int _orderCount = 0;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  Future<void> _loadProfile() async {
    try {
      final res = await AuthService.me();
      final user = res['user'] as Map<String, dynamic>? ?? {};
      if (mounted) {
        setState(() {
          _fullName = user['full_name']?.toString() ?? '';
          _email = user['email']?.toString() ?? '';
          _orderCount = (user['order_count'] as num?)?.toInt() ?? 0;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _initials() {
    final parts = _fullName.trim().split(' ');
    if (parts.isEmpty || parts.first.isEmpty) return '?';
    if (parts.length == 1) return parts.first[0].toUpperCase();
    return (parts.first[0] + parts.last[0]).toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text("Profile")),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ////// User Info Card ///////
                  Card(
                    elevation: 0.5,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: ListTile(
                      leading: CircleAvatar(
                        radius: 24,
                        backgroundColor:
                            theme.colorScheme.primary.withOpacity(0.2),
                        child: Text(
                          _initials(),
                          style: TextStyle(
                            color: theme.colorScheme.primary,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                      title: Text(
                        _fullName.isNotEmpty ? _fullName : 'Loading…',
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                      subtitle: Text(
                        _email.isNotEmpty ? _email : '',
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),

                  ////// Profile Options ///////
                  _buildProfileTile(
                    context,
                    Icons.person_outline,
                    "Profile",
                    "Manage your account",
                    onTap: () async {
                      await Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => const PersonalInfoScreen(),
                        ),
                      );
                      // Refresh profile data when returning from edit screen
                      _loadProfile();
                    },
                  ),
                  _buildProfileTile(
                    context,
                    Icons.history,
                    "Order History",
                    "$_orderCount order${_orderCount == 1 ? '' : 's'}",
                    onTap: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                            builder: (_) => const OrderHistoryScreen()),
                      );
                    },
                  ),
                  _buildProfileTile(
                    context,
                    Icons.favorite_border,
                    "Favorites",
                    "Your saved items",
                    onTap: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                            builder: (_) => const FavoritesScreen()),
                      );
                    },
                  ),
                  _buildProfileTile(
                    context,
                    Icons.settings_outlined,
                    "Settings",
                    "Preferences and more",
                    onTap: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                            builder: (_) => const SettingsScreen()),
                      );
                    },
                  ),
                ],
              ),
            ),
    );
  }

  Widget _buildProfileTile(BuildContext context, IconData icon, String title,
      String subtitle, {VoidCallback? onTap}) {
    return Card(
      elevation: 0.3,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: ListTile(
        leading: Icon(icon, color: Colors.orangeAccent),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}

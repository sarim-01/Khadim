import 'package:flutter/material.dart';
import 'package:khaadim/services/token_storage.dart';
import 'package:khaadim/screens/auth/login_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({Key? key}) : super(key: key);

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool pushNotifications = true;
  bool emailNotifications = true;
  bool orderUpdates = true;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SafeArea(
      child: Scaffold(
        appBar: AppBar(
          leading: IconButton(
            icon: const Icon(Icons.arrow_back),
            onPressed: () => Navigator.pop(context),
          ),
          title: const Text("Settings"),
        ),
        floatingActionButton: FloatingActionButton(
          backgroundColor: theme.colorScheme.primary,
          foregroundColor: Colors.black,
          onPressed: () {},
          child: const Icon(Icons.mic_none_rounded),
        ),
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ////// Notifications Section ///////
              Text(
                "Notifications",
                style: theme.textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              _buildSwitchTile(
                icon: Icons.notifications_outlined,
                title: "Push Notifications",
                value: pushNotifications,
                onChanged: (val) => setState(() => pushNotifications = val),
              ),
              _buildSwitchTile(
                icon: Icons.email_outlined,
                title: "Email Notifications",
                value: emailNotifications,
                onChanged: (val) => setState(() => emailNotifications = val),
              ),
              _buildSwitchTile(
                icon: Icons.shopping_bag_outlined,
                title: "Order Updates",
                value: orderUpdates,
                onChanged: (val) => setState(() => orderUpdates = val),
              ),
              const SizedBox(height: 24),

              ////// Support Section ///////
              Text(
                "Support",
                style: theme.textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              _buildOptionTile(
                  icon: Icons.support_agent_outlined, title: "Contact Support"),
              _buildOptionTile(
                  icon: Icons.privacy_tip_outlined, title: "Privacy Policy"),
              _buildOptionTile(
                  icon: Icons.description_outlined,
                  title: "Terms of Service"),
              const SizedBox(height: 24),

              ////// Account Section ///////
              Text(
                "Account",
                style: theme.textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              _buildOptionTile(
                icon: Icons.logout,
                title: "Logout",
                color: Colors.black87,
                onTap: () async {
                  // Show loading indicator or directly logout
                  await TokenStorage.clearToken();
                  if (!mounted) return;
                  Navigator.pushAndRemoveUntil(
                    context,
                    MaterialPageRoute(builder: (_) => const LoginScreen()),
                    (route) => false,
                  );
                },
              ),
              _buildOptionTile(
                icon: Icons.delete_outline,
                title: "Delete Account",
                color: Colors.redAccent,
                onTap: () {
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text("Account deletion feature coming soon")));
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  ////// Helper Widgets ///////
  Widget _buildSwitchTile({
    required IconData icon,
    required String title,
    required bool value,
    required Function(bool) onChanged,
  }) {
    return Card(
      elevation: 0.3,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: SwitchListTile(
        value: value,
        onChanged: onChanged,
        title: Text(title),
        secondary: Icon(icon, color: Colors.orangeAccent),
        activeColor: Colors.orangeAccent,
      ),
    );
  }

  Widget _buildOptionTile({
    required IconData icon,
    required String title,
    Color? color,
    VoidCallback? onTap,
  }) {
    return Card(
      elevation: 0.3,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: ListTile(
        leading: Icon(icon, color: color ?? Colors.orangeAccent),
        title: Text(title),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:khaadim/app_config.dart';
import 'package:khaadim/models/menu_item.dart';
import 'package:khaadim/providers/dine_in_provider.dart';
import 'package:khaadim/screens/dine_in/kiosk_bottom_nav.dart';
import 'package:khaadim/services/menu_service.dart';
import 'package:khaadim/services/api_config.dart';
import 'package:khaadim/utils/ImageResolver.dart';
import 'package:khaadim/services/favorites_service.dart';
import 'package:khaadim/widgets/kiosk_voice_fab.dart';
import 'package:khaadim/providers/favourites_notifier.dart';
import 'package:provider/provider.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/screens/cart/cart_screen.dart';


class MenuScreen extends StatefulWidget {
  /// Optional pre-selected cuisine filter. Accepts any common variant
  /// (e.g. "bbq", "BBQ", "fast_food", "fast food"). Value is normalized
  /// to match the chip labels in [_MenuScreenState.cuisines].
  final String? initialCuisine;

  /// Optional pre-selected category filter (e.g. "drink", "main").
  final String? initialCategory;

  /// Optional pre-filled search query that mirrors typing in the search
  /// bar on launch — useful when the user names a specific dish by voice.
  final String? initialSearch;

  const MenuScreen({
    super.key,
    this.initialCuisine,
    this.initialCategory,
    this.initialSearch,
  });

  @override
  State<MenuScreen> createState() => _MenuScreenState();
}

class _MenuScreenState extends State<MenuScreen> {
  List<MenuItemModel> fullMenu = [];
  List<MenuItemModel> filteredMenu = [];

  List<String> categories = ["All", "starter", "main", "side", "drink", "bread"];
  List<String> cuisines = ["All", "Fast Food", "Chinese", "Desi", "BBQ", "Drinks"];

  String selectedCategory = "All";
  String selectedCuisine = "All";
  String searchQuery = "";

  bool loading = true;
  bool _routeArgsApplied = false;
  final TextEditingController _searchController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _applyInitialFiltersFromWidget();
    loadMenu();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_routeArgsApplied) return;
    _routeArgsApplied = true;

    // Voice navigation hands us filters via Navigator.pushNamed(arguments:).
    // Constructor args win; route args fill any still-default slots so
    // both entry points work without clobbering each other.
    final raw = ModalRoute.of(context)?.settings.arguments;
    if (raw is! Map) return;

    String? readString(String key) {
      final v = raw[key];
      if (v == null) return null;
      final s = v.toString().trim();
      return s.isEmpty ? null : s;
    }

    bool changed = false;

    final routeCuisine = readString('cuisine') ?? readString('cuisine_filter');
    if (routeCuisine != null && selectedCuisine == 'All') {
      final label = _normalizeCuisineLabel(routeCuisine);
      if (label != null) {
        selectedCuisine = label;
        changed = true;
      }
    }

    final routeCategory =
        readString('category') ?? readString('category_filter');
    if (routeCategory != null && selectedCategory == 'All') {
      final label = _normalizeCategoryLabel(routeCategory);
      if (label != null) {
        selectedCategory = label;
        changed = true;
      }
    }

    final routeSearch = readString('search') ?? readString('query');
    if (routeSearch != null && searchQuery.isEmpty) {
      searchQuery = routeSearch;
      _searchController.text = routeSearch;
      changed = true;
    }

    if (changed) {
      applyFilters();
    }
  }

  /// Seed filter state from constructor arguments. Called from initState so
  /// the very first [applyFilters] (triggered by [loadMenu]) honours voice
  /// pre-selections without waiting for a rebuild.
  void _applyInitialFiltersFromWidget() {
    final cuisine = widget.initialCuisine;
    if (cuisine != null && cuisine.trim().isNotEmpty) {
      final label = _normalizeCuisineLabel(cuisine);
      if (label != null) selectedCuisine = label;
    }

    final category = widget.initialCategory;
    if (category != null && category.trim().isNotEmpty) {
      final label = _normalizeCategoryLabel(category);
      if (label != null) selectedCategory = label;
    }

    final search = widget.initialSearch;
    if (search != null && search.trim().isNotEmpty) {
      searchQuery = search.trim();
      _searchController.text = searchQuery;
    }
  }

  /// Map whatever shape the voice pipeline sends us onto the chip labels
  /// already defined in [cuisines]. Returns null for unknown values so the
  /// caller can simply leave the default "All" in place.
  String? _normalizeCuisineLabel(String raw) {
    final t = raw.trim().toLowerCase();
    if (t.isEmpty || t == 'all') return null;

    for (final label in cuisines) {
      if (label == 'All') continue;
      if (label.toLowerCase() == t) return label;
    }

    if (t == 'bbq' ||
        t.contains('barbe') ||
        t.contains('tikka') ||
        t.contains('boti') ||
        t.contains('grill')) {
      return 'BBQ';
    }
    if (t.contains('chinese') ||
        t.contains('chow') ||
        t.contains('manchur') ||
        t.contains('szechuan')) {
      return 'Chinese';
    }
    if (t.contains('desi') ||
        t.contains('pakistani') ||
        t.contains('karahi') ||
        t.contains('biryani') ||
        t.contains('nihari')) {
      return 'Desi';
    }
    if (t.contains('fast') ||
        t == 'fast_food' ||
        t == 'fastfood' ||
        t.contains('burger') ||
        t.contains('zinger') ||
        t.contains('fries') ||
        t.contains('nugget')) {
      return 'Fast Food';
    }
    if (t.contains('drink') ||
        t.contains('beverage') ||
        t.contains('cola') ||
        t.contains('juice') ||
        t.contains('chai') ||
        t.contains('tea')) {
      return 'Drinks';
    }
    return null;
  }

  /// Collapse common category synonyms onto the exact chip values used by
  /// [categories]. "drinks" → "drink", "mains" → "main", etc.
  String? _normalizeCategoryLabel(String raw) {
    final t = raw.trim().toLowerCase();
    if (t.isEmpty || t == 'all') return null;

    for (final label in categories) {
      if (label == 'All') continue;
      if (label.toLowerCase() == t) return label;
    }

    if (t.startsWith('starter') || t.contains('appetiz')) return 'starter';
    if (t.startsWith('main')) return 'main';
    if (t.startsWith('side')) return 'side';
    if (t.startsWith('drink') || t.startsWith('beverage')) return 'drink';
    if (t.startsWith('bread') || t.contains('naan') || t.contains('roti')) {
      return 'bread';
    }
    return null;
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> loadMenu() async {
    try {
      fullMenu = await MenuService.fetchMenu();
      filteredMenu = fullMenu;
    } catch (e) {
      print("Error: $e");
    }
    if (!mounted) return;
    setState(() => loading = false);

    // Filters seeded from the voice pipeline (or route arguments) must be
    // reapplied after the menu arrives, otherwise the user lands on the
    // unfiltered list even though the chips already look selected.
    if (selectedCuisine != 'All' ||
        selectedCategory != 'All' ||
        searchQuery.isNotEmpty) {
      applyFilters();
    }
  }

  void applyFilters() {
    setState(() {
      filteredMenu = fullMenu.where((item) {
        final matchesCategory =
            selectedCategory == "All" || item.itemCategory == selectedCategory;
        final matchesCuisine =
            selectedCuisine == "All" || item.itemCuisine == selectedCuisine;
        final matchesSearch =
            item.itemName.toLowerCase().contains(searchQuery.toLowerCase());
        return matchesCategory && matchesCuisine && matchesSearch;
      }).toList();
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text("Menu"),
        actions: [
          IconButton(
            icon: const Icon(Icons.shopping_cart_outlined),
            onPressed: () {
              if (AppConfig.isKiosk) {
                Navigator.pushNamed(context, '/kiosk-cart');
              } else {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const CartScreen()),
                );
              }
            },
          ),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: loadMenu,
              child: Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.all(12),
                    child: TextField(
                      controller: _searchController,
                      onChanged: (value) {
                        searchQuery = value;
                        applyFilters();
                      },
                      decoration: InputDecoration(
                        hintText: "Search menu…",
                        prefixIcon: const Icon(Icons.search),
                        filled: true,
                        fillColor: theme.colorScheme.surface,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide.none,
                        ),
                      ),
                    ),
                  ),
                  SizedBox(
                    height: 40,
                    child: ListView.builder(
                      scrollDirection: Axis.horizontal,
                      itemCount: categories.length,
                      itemBuilder: (_, index) {
                        final cat = categories[index];
                        final isSelected = cat == selectedCategory;
                        return Padding(
                          padding: const EdgeInsets.only(left: 8),
                          child: ChoiceChip(
                            label: Text(cat),
                            selected: isSelected,
                            onSelected: (_) {
                              selectedCategory = cat;
                              applyFilters();
                            },
                          ),
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 10),
                  SizedBox(
                    height: 40,
                    child: ListView.builder(
                      scrollDirection: Axis.horizontal,
                      itemCount: cuisines.length,
                      itemBuilder: (_, index) {
                        final cu = cuisines[index];
                        final isSelected = cu == selectedCuisine;
                        return Padding(
                          padding: const EdgeInsets.only(left: 8),
                          child: ChoiceChip(
                            label: Text(cu),
                            selected: isSelected,
                            onSelected: (_) {
                              selectedCuisine = cu;
                              applyFilters();
                            },
                          ),
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 10),
                  Expanded(
                    child: ListView.builder(
                      padding: const EdgeInsets.all(12),
                      itemCount: filteredMenu.length,
                      itemBuilder: (_, i) => _MenuItemCard(
                        item: filteredMenu[i],
                      ),
                    ),
                  ),
                ],
              ),
            ),
      bottomNavigationBar: AppConfig.isKiosk
          ? const KioskBottomNav(currentIndex: 1)
          : null,
      floatingActionButton:
          AppConfig.isKiosk ? const KioskVoiceFab() : null,
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Stateful card — owns its own favourite state so toggling is instant
// ─────────────────────────────────────────────────────────────────────────────
class _MenuItemCard extends StatefulWidget {
  final MenuItemModel item;
  const _MenuItemCard({required this.item});

  @override
  State<_MenuItemCard> createState() => _MenuItemCardState();
}

class _MenuItemCardState extends State<_MenuItemCard> {
  bool _isFav = false;
  bool _favLoading = true;
  bool _toggling = false;

  @override
  void initState() {
    super.initState();
    if (AppConfig.isKiosk) {
      _favLoading = false;
    } else {
      _loadFavStatus();
      // Listen to voice-driven favourite changes
      FavouritesNotifier.instance.addListener(_onNotifierChanged);
    }
  }

  @override
  void dispose() {
    FavouritesNotifier.instance.removeListener(_onNotifierChanged);
    super.dispose();
  }

  void _onNotifierChanged() {
    if (!mounted) return;
    final newFav = FavouritesNotifier.instance.isItemFav(widget.item.itemId);
    if (newFav != _isFav) {
      setState(() => _isFav = newFav);
    }
  }

  Future<void> _loadFavStatus() async {
    try {
      final res = await FavouritesService.getFavouriteStatus(
        itemId: widget.item.itemId,
      );
      if (mounted) {
        final isFav = res['is_favourite'] == true;
        // Keep notifier in sync with server state
        FavouritesNotifier.instance.updateItem(widget.item.itemId, added: isFav);
        setState(() {
          _isFav = isFav;
          _favLoading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _favLoading = false);
    }
  }

  Future<void> _toggle() async {
    if (_toggling) return;
    setState(() => _toggling = true);
    try {
      final res = await FavouritesService.toggleFavourite(
        itemId: widget.item.itemId,
      );
      if (!mounted) return;
      final added = res['action'] == 'added';
      // Keep the global notifier in sync for voice-driven cards too
      FavouritesNotifier.instance.updateItem(widget.item.itemId, added: added);
      setState(() => _isFav = added);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content:
            Text(added ? 'Added to favourites' : 'Removed from favourites'),
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 1),
      ));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString()), behavior: SnackBarBehavior.floating),
      );
    } finally {
      if (mounted) setState(() => _toggling = false);
    }
  }

  Widget _menuImage() {
    final raw = widget.item.imageUrl.trim();
    final networkUrl = ApiConfig.resolvePublicImageUrl(raw);
    if (networkUrl != null) {
      return Image.network(
        networkUrl,
        height: 110,
        width: 110,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => _fallbackImage(),
      );
    }
    return _fallbackImage();
  }

  Widget _fallbackImage() {
    final category = ImageResolver.normalizeCuisineForMenuImage(
        widget.item.itemCuisine);
    final fallback = ImageResolver.getMenuImage(category, widget.item.itemName);
    return Image.asset(fallback,
        height: 110, width: 110, fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => Container(
              height: 110,
              width: 110,
              color: Colors.grey[300],
              child: const Icon(Icons.image_not_supported, size: 40),
            ));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: theme.colorScheme.surface,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.06),
            blurRadius: 6,
            offset: const Offset(0, 3),
          )
        ],
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(16),
              bottomLeft: Radius.circular(16),
            ),
            child: _menuImage(),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          widget.item.itemName,
                          style: theme.textTheme.titleSmall!
                              .copyWith(fontWeight: FontWeight.bold),
                        ),
                      ),
                      if (!AppConfig.isKiosk)
                        _favLoading
                            ? const SizedBox(
                                width: 24,
                                height: 24,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : GestureDetector(
                                onTap: _toggle,
                                child: Icon(
                                  _isFav
                                      ? Icons.favorite
                                      : Icons.favorite_border,
                                  color: _isFav ? Colors.redAccent : Colors.grey,
                                  size: 22,
                                ),
                              ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    widget.item.itemDescription,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          "Rs ${widget.item.itemPrice}",
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: theme.colorScheme.primary,
                          ),
                        ),
                      ),
                      AppConfig.isKiosk
                          ? ElevatedButton(
                              onPressed: () {
                                Provider.of<DineInProvider>(context,
                                        listen: false)
                                    .addItem(
                                  widget.item.itemId,
                                  'menu_item',
                                  widget.item.itemName,
                                  widget.item.itemPrice.toDouble(),
                                  1,
                                );
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(
                                    content: Text("${widget.item.itemName} added"),
                                    behavior: SnackBarBehavior.floating,
                                    duration: const Duration(seconds: 1),
                                  ),
                                );
                              },
                              style: ElevatedButton.styleFrom(
                                backgroundColor: Colors.orange,
                              ),
                              child: const Text("Add"),
                            )
                          : Consumer<CartProvider>(
                              builder: (context, cart, child) {
                                return ElevatedButton(
                                  onPressed: cart.isSyncing
                                      ? null
                                      : () async {
                                          try {
                                            await cart.addMenuItem(widget.item);
                                            if (!context.mounted) return;
                                            ScaffoldMessenger.of(context)
                                                .showSnackBar(SnackBar(
                                              content: Text(
                                                  "${widget.item.itemName} added to cart"),
                                              behavior:
                                                  SnackBarBehavior.floating,
                                              duration:
                                                  const Duration(seconds: 1),
                                            ));
                                          } catch (e) {
                                            if (!context.mounted) return;
                                            ScaffoldMessenger.of(context)
                                                .showSnackBar(SnackBar(
                                              content: Text(e.toString()),
                                              behavior:
                                                  SnackBarBehavior.floating,
                                            ));
                                          }
                                        },
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: Colors.orange,
                                  ),
                                  child: const Text("Add"),
                                );
                              },
                            ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

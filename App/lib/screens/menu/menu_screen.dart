import 'package:flutter/material.dart';
import 'package:khaadim/models/menu_item.dart';
import 'package:khaadim/services/menu_service.dart';
import 'package:khaadim/utils/ImageResolver.dart';
import 'package:khaadim/services/favorites_service.dart';
import 'package:provider/provider.dart';
import 'package:khaadim/providers/cart_provider.dart';


class MenuScreen extends StatefulWidget {
  const MenuScreen({Key? key}) : super(key: key);

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

  @override
  void initState() {
    super.initState();
    loadMenu();
  }

  Future<void> loadMenu() async {
    try {
      fullMenu = await MenuService.fetchMenu();
      filteredMenu = fullMenu;
    } catch (e) {
      print("Error: $e");
    }
    setState(() => loading = false);
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

  final Map<String, String> localMenuImages = {
    "Burger": "assets/images/menu/fast_food/burger.jpeg",
    "Chicken Burger": "assets/images/menu/fast_food/chicken_burger.jpeg",
    "Fries": "assets/images/menu/fast_food/fries.jpeg",
    "Loaded Fries": "assets/images/menu/fast_food/loaded_fries.jpeg",
    "Nuggets": "assets/images/menu/fast_food/nuggets.jpeg",
    "Beef Boti": "assets/images/menu/bbq/beef_boti.jpeg",
    "Chicken Tikka": "assets/images/menu/bbq/chicken_tikka.jpeg",
    "Grilled Fish": "assets/images/menu/bbq/grilled_fish.jpeg",
    "Malai Boti": "assets/images/menu/bbq/malai_boti.jpeg",
    "Reshmi Kebab": "assets/images/menu/bbq/reshmi_kebab.jpeg",
    "Garlic Naan": "assets/images/menu/bread/garlic_naan.jpeg",
    "Naan": "assets/images/menu/bread/naan.jpeg",
    "Paratha": "assets/images/menu/bread/paratha.jpeg",
    "Roti": "assets/images/menu/bread/roti.jpeg",
    "Chow Mein": "assets/images/menu/chinese/chow_mein.jpeg",
    "Hot Sour Soup": "assets/images/menu/chinese/hot_sour_soup.jpeg",
    "Kung Pao": "assets/images/menu/chinese/kung_pao.jpeg",
    "Manchurian": "assets/images/menu/chinese/manchurian.jpeg",
    "Spring Rolls": "assets/images/menu/chinese/spring_rolls.jpeg",
    "Biryani": "assets/images/menu/desi/biryani.jpeg",
    "Chana Chaat": "assets/images/menu/desi/chana_chaat.jpeg",
    "Chicken Karahi": "assets/images/menu/desi/chicken_karahi.jpeg",
    "Daal Chawal": "assets/images/menu/desi/daal_chawal.jpeg",
    "Nihari": "assets/images/menu/desi/nihari.jpeg",
    "Samosa": "assets/images/menu/desi/samosa.jpeg",
    "Chai": "assets/images/menu/drinks/chai.jpeg",
    "Cola": "assets/images/menu/drinks/cola.jpeg",
    "Iced Coffee": "assets/images/menu/drinks/iced_coffee.jpeg",
    "Lemonade": "assets/images/menu/drinks/lemonade.jpeg",
    "Mint Margarita": "assets/images/menu/drinks/mint_margarita.jpeg",
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text("Menu")),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: loadMenu,
              child: Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.all(12),
                    child: TextField(
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
    _loadFavStatus();
  }

  Future<void> _loadFavStatus() async {
    try {
      final res = await FavouritesService.getFavouriteStatus(
        itemId: widget.item.itemId,
      );
      if (mounted) {
        setState(() {
          _isFav = res['is_favourite'] == true;
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
    final url = widget.item.imageUrl.trim();
    final hasUrl =
        url.isNotEmpty && (url.startsWith('http://') || url.startsWith('https://'));
    if (hasUrl) {
      return Image.network(url,
          height: 110, width: 110, fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => _fallbackImage());
    }
    return _fallbackImage();
  }

  Widget _fallbackImage() {
    final category =
        widget.item.itemCuisine.toLowerCase().replaceAll(' ', '_');
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
                      // Heart button
                      _favLoading
                          ? const SizedBox(
                              width: 24, height: 24,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : GestureDetector(
                              onTap: _toggle,
                              child: Icon(
                                _isFav ? Icons.favorite : Icons.favorite_border,
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
                      Consumer<CartProvider>(
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
                                        behavior: SnackBarBehavior.floating,
                                        duration: const Duration(seconds: 1),
                                      ));
                                    } catch (e) {
                                      if (!context.mounted) return;
                                      ScaffoldMessenger.of(context)
                                          .showSnackBar(SnackBar(
                                        content: Text(e.toString()),
                                        behavior: SnackBarBehavior.floating,
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

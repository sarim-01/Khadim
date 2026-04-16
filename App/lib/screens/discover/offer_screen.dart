import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:khaadim/app_config.dart';

import 'package:khaadim/models/offer_model.dart';
import 'package:khaadim/models/deal_model.dart';
import 'package:khaadim/services/offer_service.dart';
import 'package:khaadim/services/deal_service.dart';
import 'package:khaadim/services/favorites_service.dart';
import 'package:khaadim/providers/cart_provider.dart';
import 'package:khaadim/providers/dine_in_provider.dart';
import 'package:khaadim/screens/dine_in/kiosk_bottom_nav.dart';
import 'package:khaadim/utils/ImageResolver.dart';
import 'package:khaadim/screens/cart/cart_screen.dart';

class OffersScreen extends StatefulWidget {
  const OffersScreen({super.key});

  @override
  State<OffersScreen> createState() => _OffersScreenState();
}

class _OffersScreenState extends State<OffersScreen> {
  final PageController _pageController = PageController();
  int _currentPage = 0;

  List<OfferModel> offers = [];
  List<DealModel> deals = [];
  bool loading = true;

  // ── Deal filters ────────────────────────────────────────────
  String _searchQuery = '';
  String _selectedCuisine = 'All';
  String _selectedServing = 'All';

  static const List<String> _cuisineFilters = [
    'All',
    'Fast Food',
    'Chinese',
    'BBQ',
    'Desi',
  ];
  static const List<String> _servingFilters = ['All', '1', '2', '3', '4', '5+'];

  static const Map<String, List<String>> _dealImagePoolByCuisine = {
    'bbq': [
      'assets/images/deals/BBQ deals/bbq_solo.png',
      'assets/images/deals/BBQ deals/bbq duo.png',
      'assets/images/deals/BBQ deals/bbq_squad.png',
      'assets/images/deals/BBQ deals/bbq_party_A.png',
      'assets/images/deals/BBQ deals/bbq_party_B.png',
    ],
    'chinese': [
      'assets/images/deals/Chinese Deals/chinese_solo.png',
      'assets/images/deals/Chinese Deals/chinese_duo.png',
      'assets/images/deals/Chinese Deals/chinese_squad_A.png',
      'assets/images/deals/Chinese Deals/Chinese_Squad_B.png',
      'assets/images/deals/Chinese Deals/chinese_party.png',
    ],
    'desi': [
      'assets/images/deals/Desi deals/desi_solo.png',
      'assets/images/deals/Desi deals/desi_duo.png',
      'assets/images/deals/Desi deals/desi_squad_A.png',
      'assets/images/deals/Desi deals/desi_squad_B.png',
      'assets/images/deals/Desi deals/desi_party.png',
    ],
    'fast_food': [
      'assets/images/deals/FastFood deals/Fast_solo_A.png',
      'assets/images/deals/FastFood deals/Fast_solo_B.png',
      'assets/images/deals/FastFood deals/Fast_Duo.png',
      'assets/images/deals/FastFood deals/Fast_squad.png',
      'assets/images/deals/FastFood deals/Fast_food_big_party.png',
    ],
  };

  List<DealModel> get _filteredDeals {
    return deals.where((d) {
      final q = _searchQuery.toLowerCase();
      final matchesSearch = q.isEmpty ||
          d.dealName.toLowerCase().contains(q) ||
          d.items.toLowerCase().contains(q);

      final matchesCuisine = _selectedCuisine == 'All' ||
          d.dealName.toLowerCase().contains(
                _selectedCuisine.toLowerCase().replaceAll(' ', ''),
              ) ||
          d.dealName.toLowerCase().startsWith(
                _selectedCuisine.split(' ').first.toLowerCase(),
              );

      final matchesServing = _selectedServing == 'All' ||
          (() {
            if (_selectedServing == '5+') return d.servingSize >= 5;
            return d.servingSize == int.tryParse(_selectedServing);
          })();

      return matchesSearch && matchesCuisine && matchesServing;
    }).toList();
  }

  String _resolveDealImage(DealModel deal) {
    final raw = deal.imageUrl.trim();
    if (raw.isNotEmpty) {
      // Normalize DB-provided local asset paths.
      final normalized =
          raw.replaceAll('\\', '/').replaceFirst(RegExp(r'^/+'), '');
      final lower = normalized.toLowerCase();

      // Ignore known placeholder values from backend and fall back to deal mapping.
      final isPlaceholder = lower.endsWith('confirm.png') ||
          lower.contains('/confirm.') ||
          lower.contains('placeholder');

      if (!isPlaceholder) {
        if (normalized.startsWith('assets/')) {
          return normalized;
        }
        if (normalized.startsWith('images/')) {
          return 'assets/$normalized';
        }
        if (normalized.startsWith('deals/')) {
          return 'assets/images/$normalized';
        }
      }
    }

    final mapped = ImageResolver.getDealImage(deal.dealName);
    if (mapped != ImageResolver.fallbackImage) {
      return mapped;
    }

    final cuisine = _inferDealCuisine(deal);
    if (cuisine != null) {
      final pool = _dealImagePoolByCuisine[cuisine];
      if (pool != null && pool.isNotEmpty) {
        return pool[deal.dealId % pool.length];
      }
    }

    return ImageResolver.fallbackImage;
  }

  String? _inferDealCuisine(DealModel deal) {
    final hay = '${deal.dealName} ${deal.items}'.toLowerCase();

    if (hay.contains('bbq') ||
        hay.contains('tikka') ||
        hay.contains('boti') ||
        hay.contains('kebab') ||
        hay.contains('grill')) {
      return 'bbq';
    }

    if (hay.contains('chinese') ||
        hay.contains('manchurian') ||
        hay.contains('chow') ||
        hay.contains('szechuan') ||
        hay.contains('kung pao')) {
      return 'chinese';
    }

    if (hay.contains('desi') ||
        hay.contains('karahi') ||
        hay.contains('biryani') ||
        hay.contains('nihari') ||
        hay.contains('paratha') ||
        hay.contains('daal')) {
      return 'desi';
    }

    if (hay.contains('fast') ||
        hay.contains('burger') ||
        hay.contains('fries') ||
        hay.contains('nugget') ||
        hay.contains('sandwich') ||
        hay.contains('zinger')) {
      return 'fast_food';
    }

    return null;
  }

  /// Map offer category -> banner image
  final Map<String, String> offerBannerImages = const {
    "Fast Food": "assets/images/deals/FastFood deals/Fast_solo_A.png",
    "Chinese": "assets/images/deals/Chinese Deals/chinese_solo.png",
    "Desi": "assets/images/deals/Desi deals/desi_solo.png",
    "BBQ": "assets/images/deals/BBQ deals/bbq_solo.png",
    "Drinks": "assets/images/confirm.png",
  };

  @override
  void initState() {
    super.initState();
    _loadData();
    _startAutoSlide();
  }

  Future<void> _loadData() async {
    try {
      final fetchedOffers = await OfferService.fetchOffers();
      final fetchedDeals = await DealService.fetchDeals();

      setState(() {
        offers = fetchedOffers;
        deals = fetchedDeals;
        loading = false;
      });
    } catch (e) {
      debugPrint("Error loading offers/deals: $e");
      setState(() {
        loading = false;
      });
    }
  }

  void _startAutoSlide() {
    // simple loop; will keep sliding as long as widget is alive
    Future.doWhile(() async {
      await Future.delayed(const Duration(seconds: 4));

      if (!mounted || !_pageController.hasClients || offers.isEmpty) {
        return true; // continue loop but nothing to slide if no offers
      }

      _currentPage = (_currentPage + 1) % offers.length;

      _pageController.animateToPage(
        _currentPage,
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeInOut,
      );

      return true;
    });
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SafeArea(
      child: Scaffold(
        appBar: AppBar(
          title: const Text("Offers & Deals"),
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
                onRefresh: _loadData,
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    // ==========================
                    //     BANNERS (OFFERS)
                    // ==========================
                    if (offers.isNotEmpty) ...[
                      SizedBox(
                        height: 180,
                        child: PageView.builder(
                          controller: _pageController,
                          itemCount: offers.length,
                          onPageChanged: (index) {
                            setState(() => _currentPage = index);
                          },
                          itemBuilder: (_, index) {
                            final offer = offers[index];
                            final bannerImage =
                                offerBannerImages[offer.category] ??
                                    offerBannerImages["Fast Food"]!;

                            return AnimatedContainer(
                              duration: const Duration(milliseconds: 400),
                              margin: const EdgeInsets.symmetric(horizontal: 8),
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(16),
                                image: DecorationImage(
                                  image: AssetImage(bannerImage),
                                  fit: BoxFit.cover,
                                  onError: (_, __) {},
                                ),
                              ),
                              child: Container(
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(16),
                                  gradient: LinearGradient(
                                    colors: [
                                      Colors.black.withOpacity(0.5),
                                      Colors.transparent,
                                    ],
                                    begin: Alignment.bottomCenter,
                                    end: Alignment.topCenter,
                                  ),
                                ),
                                padding: const EdgeInsets.all(12),
                                alignment: Alignment.bottomLeft,
                                child: Text(
                                  offer.title,
                                  style: theme.textTheme.titleMedium?.copyWith(
                                    color: Colors.white,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                      ),

                      const SizedBox(height: 10),

                      // DOT INDICATORS
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: List.generate(
                          offers.length,
                          (index) => AnimatedContainer(
                            duration: const Duration(milliseconds: 300),
                            margin: const EdgeInsets.symmetric(horizontal: 4),
                            width: _currentPage == index ? 12 : 8,
                            height: 8,
                            decoration: BoxDecoration(
                              color: _currentPage == index
                                  ? Colors.orangeAccent
                                  : Colors.grey,
                              borderRadius: BorderRadius.circular(8),
                            ),
                          ),
                        ),
                      ),

                      const SizedBox(height: 24),
                    ],

                    // ==========================
                    //     OFFERS LIST (TEXT)
                    // ==========================
                    if (offers.isNotEmpty) ...[
                      Text(
                        "Promotional Offers",
                        style: theme.textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 12),
                      ...offers.map((offer) {
                        final img = offerBannerImages[offer.category] ??
                            offerBannerImages["Fast Food"]!;

                        return Padding(
                          padding: const EdgeInsets.only(bottom: 16),
                          child: _buildOfferCard(
                            context,
                            title: offer.title,
                            description: offer.description,
                            image: img,
                            validity: "Valid till ${offer.validity}",
                            code: offer.offerCode,
                          ),
                        );
                      }),
                      const SizedBox(height: 24),
                    ],

                    // ==========================
                    //       DEALS LIST
                    // ==========================
                    Text(
                      "Combo Deals",
                      style: theme.textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 12),

                    // Search bar
                    TextField(
                      onChanged: (v) => setState(() => _searchQuery = v),
                      decoration: InputDecoration(
                        hintText: 'Search deals…',
                        prefixIcon: const Icon(Icons.search),
                        filled: true,
                        fillColor: theme.colorScheme.surface,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide.none,
                        ),
                        contentPadding: const EdgeInsets.symmetric(
                          vertical: 10,
                          horizontal: 12,
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),

                    // Cuisine filter chips
                    SizedBox(
                      height: 38,
                      child: ListView(
                        scrollDirection: Axis.horizontal,
                        children: _cuisineFilters.map((c) {
                          final selected = c == _selectedCuisine;
                          return Padding(
                            padding: const EdgeInsets.only(right: 8),
                            child: ChoiceChip(
                              label: Text(c),
                              selected: selected,
                              onSelected: (_) =>
                                  setState(() => _selectedCuisine = c),
                            ),
                          );
                        }).toList(),
                      ),
                    ),
                    const SizedBox(height: 8),

                    // Serving size filter chips
                    SizedBox(
                      height: 38,
                      child: ListView(
                        scrollDirection: Axis.horizontal,
                        children: _servingFilters.map((s) {
                          final selected = s == _selectedServing;
                          return Padding(
                            padding: const EdgeInsets.only(right: 8),
                            child: ChoiceChip(
                              label: Text(
                                s == 'All' ? 'All Sizes' : '$s Person',
                              ),
                              selected: selected,
                              onSelected: (_) =>
                                  setState(() => _selectedServing = s),
                            ),
                          );
                        }).toList(),
                      ),
                    ),
                    const SizedBox(height: 12),

                    // Results count
                    if (_searchQuery.isNotEmpty ||
                        _selectedCuisine != 'All' ||
                        _selectedServing != 'All')
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Text(
                          '${_filteredDeals.length} deal${_filteredDeals.length == 1 ? '' : 's'} found',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.hintColor,
                          ),
                        ),
                      ),

                    if (_filteredDeals.isEmpty)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 32),
                        child: Center(
                          child: Column(
                            children: [
                              const Icon(
                                Icons.search_off,
                                size: 48,
                                color: Colors.grey,
                              ),
                              const SizedBox(height: 8),
                              Text(
                                'No deals match your filters',
                                style: theme.textTheme.bodyMedium?.copyWith(
                                  color: Colors.grey,
                                ),
                              ),
                            ],
                          ),
                        ),
                      )
                    else
                      ..._filteredDeals.map((deal) {
                        final img = _resolveDealImage(deal);
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 16),
                          child: _DealCard(deal: deal, image: img),
                        );
                      }),
                  ],
                ),
              ),
        bottomNavigationBar:
            AppConfig.isKiosk ? const KioskBottomNav(currentIndex: 2) : null,
      ),
    );
  }

  /// OFFER CARD
  Widget _buildOfferCard(
    BuildContext context, {
    required String title,
    required String description,
    required String image,
    required String validity,
    required String code,
  }) {
    final theme = Theme.of(context);

    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 6,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(16),
              bottomLeft: Radius.circular(16),
            ),
            child: Image.asset(
              image,
              width: 110,
              height: 100,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Image.asset(
                ImageResolver.fallbackImage,
                width: 110,
                height: 100,
                fit: BoxFit.cover,
              ),
            ),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: theme.textTheme.bodyLarge?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  Text(description, style: theme.textTheme.bodyMedium),
                  const SizedBox(height: 8),
                  if (code.isNotEmpty)
                    Text(
                      "Use Code: $code",
                      style: TextStyle(
                        color: theme.colorScheme.primary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  const SizedBox(height: 4),
                  Text(
                    validity,
                    style: const TextStyle(color: Colors.grey, fontSize: 12),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// DEAL CARD
  Widget _buildDealCard(
    BuildContext context, {
    required String image,
    required String title,
    required String subtitle,
    required String newPrice,
    required String discount,
  }) {
    final theme = Theme.of(context);

    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 6,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          /// IMAGE
          ClipRRect(
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(16),
              topRight: Radius.circular(16),
            ),
            child: Image.asset(
              image,
              height: 160,
              width: double.infinity,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Image.asset(
                ImageResolver.fallbackImage,
                height: 160,
                width: double.infinity,
                fit: BoxFit.cover,
              ),
            ),
          ),

          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                /// TITLE + SERVING SIZE
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        title,
                        style: theme.textTheme.bodyLarge?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.redAccent,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        discount,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),

                const SizedBox(height: 6),

                /// SUBTITLE
                Text(
                  subtitle,
                  style: theme.textTheme.bodyMedium,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),

                const SizedBox(height: 10),

                /// PRICE + BUTTON
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        newPrice,
                        style: TextStyle(
                          color: theme.colorScheme.primary,
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    ElevatedButton(
                      onPressed: () {},
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.orangeAccent,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 6,
                        ),
                      ),
                      child: const Text('Add'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Stateful deal card with heart toggle
// ─────────────────────────────────────────────────────────────────────────────
class _DealCard extends StatefulWidget {
  final DealModel deal;
  final String image;
  const _DealCard({required this.deal, required this.image});

  @override
  State<_DealCard> createState() => _DealCardState();
}

class _DealCardState extends State<_DealCard> {
  bool _isFav = false;
  bool _favLoading = true;
  bool _toggling = false;

  @override
  void initState() {
    super.initState();
    if (AppConfig.isKiosk) {
      _favLoading = false;
      return;
    }
    _loadFavStatus();
  }

  Future<void> _loadFavStatus() async {
    try {
      final res = await FavouritesService.getFavouriteStatus(
        dealId: widget.deal.dealId,
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
        dealId: widget.deal.dealId,
      );
      if (!mounted) return;
      final added = res['action'] == 'added';
      setState(() => _isFav = added);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            added ? 'Added to favourites' : 'Removed from favourites',
          ),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 1),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.toString()),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      if (mounted) setState(() => _toggling = false);
    }
  }

  Future<void> _handleAddDeal() async {
    if (AppConfig.isKiosk) {
      final dineIn = context.read<DineInProvider>();
      if (dineIn.sessionId == null || dineIn.sessionId!.isEmpty) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Please start a table session first.'),
            behavior: SnackBarBehavior.floating,
          ),
        );
        return;
      }

      dineIn.addItem(
        widget.deal.dealId,
        'deal',
        widget.deal.dealName,
        widget.deal.dealPrice,
        1,
      );

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${widget.deal.dealName} added to cart'),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 1),
        ),
      );
      return;
    }

    try {
      await context.read<CartProvider>().addDeal(widget.deal);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${widget.deal.dealName} added to cart'),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 1),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.toString()),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final deal = widget.deal;

    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 6,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(16),
              topRight: Radius.circular(16),
            ),
            child: Image.asset(
              widget.image,
              height: 160,
              width: double.infinity,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Image.asset(
                ImageResolver.fallbackImage,
                height: 160,
                width: double.infinity,
                fit: BoxFit.cover,
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        deal.dealName,
                        style: theme.textTheme.bodyLarge?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: 4),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.redAccent,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        '${deal.servingSize} Person',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    if (!AppConfig.isKiosk) ...[
                      const SizedBox(width: 4),
                      _favLoading
                          ? const SizedBox(
                              width: 24,
                              height: 24,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : GestureDetector(
                              onTap: _toggle,
                              child: Icon(
                                _isFav ? Icons.favorite : Icons.favorite_border,
                                color: _isFav ? Colors.redAccent : Colors.grey,
                                size: 22,
                              ),
                            ),
                    ],
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  deal.items,
                  style: theme.textTheme.bodyMedium,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        'Rs ${deal.dealPrice}',
                        style: TextStyle(
                          color: theme.colorScheme.primary,
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    ElevatedButton(
                      onPressed: _handleAddDeal,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.orangeAccent,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 6,
                        ),
                      ),
                      child: const Text('Add'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

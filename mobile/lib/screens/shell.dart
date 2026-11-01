import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api.dart';
import '../l10n.dart';
import '../main.dart';
import '../theme.dart';
import '../ui.dart';
import 'book.dart';

/// Signed-in app with the design's four tabs (.ph-tabs).
class Shell extends StatefulWidget {
  const Shell({super.key, required this.c});
  final AppController c;
  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  int tab = 0;
  int bookingsVersion = 0;
  ServiceItem? picked;   // a service tapped on the home screen opens the booking at that service
  int bookNonce = 0;

  void startBooking([ServiceItem? s]) => setState(() { tab = 1; picked = s; bookNonce++; });

  @override
  Widget build(BuildContext context) {
    final c = widget.c;
    final t = c.t;
    final b = Brand.of(c.biz);
    final pages = [
      HomeTab(c: c, onBook: startBooking, key: ValueKey('home$bookingsVersion')),
      BookFlow(c: c, initial: picked, key: ValueKey('book$bookNonce'), onDone: () => setState(() { bookingsVersion++; tab = 2; })),
      BookingsTab(c: c, key: ValueKey('bk$bookingsVersion')),
      AccountTab(c: c),
    ];
    return Scaffold(
      body: IndexedStack(index: tab, children: pages),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(color: Tokens.surface, border: Border(top: BorderSide(color: Tokens.line))),
        child: SafeArea(top: false, child: Row(children: [
          for (final (i, (label, icon)) in [(t('tab_home'), Icons.home_outlined), (t('tab_book'), Icons.event_available_outlined),
            (t('tab_bookings'), Icons.receipt_long_outlined), (t('tab_account'), Icons.person_outline)].indexed)
            Expanded(child: InkWell(
              onTap: () => setState(() => tab = i),
              child: Padding(padding: const EdgeInsets.fromLTRB(0, 8, 0, 10), child: Column(mainAxisSize: MainAxisSize.min, children: [
                Icon(icon, size: 22, color: tab == i ? b.dark : Tokens.muted),
                Text(label, style: TextStyle(fontSize: 11, color: tab == i ? b.dark : Tokens.muted, fontWeight: tab == i ? FontWeight.w700 : FontWeight.w400)),
              ])),
            )),
        ])),
      ),
    );
  }
}

String intlPhone(String phone) {
  final d = phone.replaceAll(RegExp(r'\D'), '');
  return d.length == 8 ? '965$d' : d;
}

class BranchCard extends StatelessWidget {
  const BranchCard({super.key, required this.c, required this.branch, this.onTap, this.selected = false, this.actions = true});
  final AppController c;
  final Branch branch;
  final VoidCallback? onTap;
  final bool selected, actions;
  @override
  Widget build(BuildContext context) {
    final b = Brand.of(c.biz);
    final t = c.t;
    return SCard(
      onTap: onTap, selected: selected,
      leading: CircleAvatar(radius: 18, backgroundColor: b.soft, child: Icon(Icons.storefront_outlined, size: 19, color: b.dark)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Flexible(child: Text(branch.name(c.lang), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14))),
          if (branch.recommended) ...[const SizedBox(width: 6), Pill(t('nearest'), bg: b.soft, fg: b.dark)],
        ]),
        Text([if (branch.address.isNotEmpty) branch.address, '\u2066${branch.hours}\u2069',
          if (branch.distanceKm != null) t('km', {'d': branch.distanceKm!.toStringAsFixed(1)})].join(' · '), style: cap),
        if (actions && branch.phone.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 6), child: Wrap(spacing: 6, children: [
          OutlinedButton.icon(onPressed: () => launchUrl(Uri.parse('tel:+${intlPhone(branch.phone)}')), icon: const Icon(Icons.call_outlined, size: 16), label: Text(t('call'))),
          OutlinedButton.icon(onPressed: () => launchUrl(Uri.parse('https://wa.me/${intlPhone(branch.phone)}'), mode: LaunchMode.externalApplication),
              icon: const Icon(Icons.chat_outlined, size: 16), label: Text(t('whatsapp'))),
        ])),
      ]),
    );
  }
}

class HomeTab extends StatefulWidget {
  const HomeTab({super.key, required this.c, required this.onBook});
  final AppController c;
  final void Function([ServiceItem? s]) onBook;
  @override
  State<HomeTab> createState() => _HomeTabState();
}

class _HomeTabState extends State<HomeTab> {
  Json? next;

  @override
  void initState() {
    super.initState();
    widget.c.api.bookings().then((all) {
      final up = all.where((b) => b['status'] == 'booked').toList()..sort((a, b) => (a['starts_at'] as String).compareTo(b['starts_at'] as String));
      if (mounted && up.isNotEmpty) setState(() => next = up.first);
    }).catchError((_) {});
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.c;
    final t = c.t;
    final cat = c.catalog!;
    final br = Brand.of(c.biz);
    final types = cat.branches.map((x) => x.businessType).toSet();
    final cats = cat.categories.where((x) => types.contains(x['business_type']) && cat.services.any((s) => s.category == x['id'])).toList();
    return Column(children: [
      PhHead(biz: c.biz, title: cat.salonName, subtitle: t('biz_${c.biz}'),
          trailing: TextButton(onPressed: c.toggleLang, child: Text(t('language'), style: const TextStyle(color: Tokens.ink))),
          child: Padding(padding: const EdgeInsets.only(top: 14), child: Text(t('hello', {'name': c.me!.fullName.split(' ').first}),
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: Tokens.ink)))),
      Expanded(child: ListView(padding: const EdgeInsets.all(14), children: [
        if (c.me!.points != null) Container(   // reference: dark points card
          padding: const EdgeInsets.all(16), margin: const EdgeInsets.only(bottom: 12),
          decoration: BoxDecoration(color: Tokens.ink, borderRadius: BorderRadius.circular(20)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(t('your_points'), style: const TextStyle(color: Colors.white70, fontSize: 13)),
            Text('${c.me!.points}', style: TextStyle(color: br.base, fontSize: 34, fontWeight: FontWeight.w800, height: 1.1)),
            Text(t('points_hint'), style: const TextStyle(color: Colors.white70, fontSize: 12)),
          ]),
        ),
        if (next != null) Container(
          padding: const EdgeInsets.all(14), margin: const EdgeInsets.only(bottom: 12),
          decoration: BoxDecoration(color: Tokens.surface, borderRadius: BorderRadius.circular(18), border: Border.all(color: Tokens.line)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(t('next_booking'), style: cap),
            const SizedBox(height: 2),
            Text('${next!['beneficiary_name']} — ${((next!['services'] as List).first as Json)[c.lang == 'en' ? 'name_en' : 'name_ar']}',
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
            Text(whenLabel(c, next!['starts_at'] as String), style: const TextStyle(color: Tokens.ink2)),
          ]),
        ),
        SizedBox(height: 56, child: FilledButton(key: const Key('book_now'), onPressed: () => widget.onBook(),
            style: FilledButton.styleFrom(backgroundColor: br.base, foregroundColor: Tokens.ink,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18))),
            child: Text('${t('book_now')} ✂️', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)))),
        if (cat.offers.isNotEmpty) ...[
          const SizedBox(height: 20),
          Row(children: [Expanded(child: Text(t('offers'), style: title18)), Text(t('swipe'), style: cap)]),
          const SizedBox(height: 8),
          SizedBox(height: 200, child: ListView(scrollDirection: Axis.horizontal, children: [
            for (final o in cat.offers) _OfferCard(c: c, o: o, onTap: () {
              final s = cat.services.where((x) => x.id == o['service']).firstOrNull;
              widget.onBook(s);
            }),
          ])),
        ],
        if (cats.isNotEmpty) ...[
          const SizedBox(height: 20),
          Text(t('categories'), style: title18),
          const SizedBox(height: 8),
          GridView.count(crossAxisCount: 3, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(),
              mainAxisSpacing: 8, crossAxisSpacing: 8, childAspectRatio: .9, children: [
            for (final x in cats) Material(color: Tokens.surface, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16),
                side: const BorderSide(color: Tokens.line)), child: InkWell(borderRadius: BorderRadius.circular(16),
                onTap: () => widget.onBook(cat.services.where((s) => s.category == x['id']).firstOrNull),
                child: Padding(padding: const EdgeInsets.all(8), child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                  SvcImage(url: c.api.url(cat.services.where((s) => s.category == x['id'] && s.image.isNotEmpty).firstOrNull?.image ?? ''), biz: c.biz, size: 56),
                  const SizedBox(height: 6),
                  Text((c.lang == 'en' && (x['name_en'] as String).isNotEmpty ? x['name_en'] : x['name_ar']) as String,
                      textAlign: TextAlign.center, maxLines: 2, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
                ])))),
          ]),
        ],
        const SizedBox(height: 20),
        Text(t('services'), style: title18),
        const SizedBox(height: 8),
        for (final s in cat.services.take(6)) ServiceCard(c: c, s: s, onBook: () => widget.onBook(s)),
        const SizedBox(height: 18),
        Text(t('branches'), style: title18),
        const SizedBox(height: 8),
        if (c.locationDenied) Notice(t('location_off')),
        for (final b in cat.branches) BranchCard(c: c, branch: b),
      ])),
    ]);
  }
}

/// Reference `.scard` for a service: photo, name, duration, price and a book button.
class ServiceCard extends StatelessWidget {
  const ServiceCard({super.key, required this.c, required this.s, required this.onBook});
  final AppController c;
  final ServiceItem s;
  final VoidCallback onBook;
  @override
  Widget build(BuildContext context) => SCard(
        onTap: onBook,
        leading: SvcImage(url: c.api.url(s.image), biz: c.biz),
        child: Row(children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(s.name(c.lang), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
            Text('⏱ ${s.minutes} ${c.t('min')}', style: cap),
            Text(kwd(s.price, c.lang), style: TextStyle(fontWeight: FontWeight.w700, color: Brand.of(c.biz).dark)),
          ])),
          FilledButton(onPressed: onBook, style: FilledButton.styleFrom(minimumSize: const Size(0, 36), padding: const EdgeInsets.symmetric(horizontal: 14)),
              child: Text(c.t('book'))),
        ]),
      );
}

class _OfferCard extends StatelessWidget {
  const _OfferCard({required this.c, required this.o, required this.onTap});
  final AppController c;
  final Json o;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final b = Brand.of(c.biz);
    final regular = o['regular'] as String;
    return Container(width: 190, margin: const EdgeInsetsDirectional.only(end: 10), child: Material(
      color: Tokens.surface, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18), side: const BorderSide(color: Tokens.line)),
      child: InkWell(borderRadius: BorderRadius.circular(18), onTap: onTap, child: Padding(padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SvcImage(url: c.api.url((o['image'] as String?) ?? ''), biz: c.biz, size: 56, radius: 14),
          const SizedBox(height: 8),
          Text((c.lang == 'en' && (o['name_en'] as String).isNotEmpty ? o['name_en'] : o['name_ar']) as String,
              maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
          Text(c.t('sessions_n', {'n': '${o['sessions']}'}), style: cap),
          const Spacer(),
          Row(children: [
            Text(kwd(o['price'] as String, c.lang), style: TextStyle(fontWeight: FontWeight.w800, color: b.dark, fontSize: 15)),
            const SizedBox(width: 6),
            if (regular != o['price']) Text(kwd(regular, c.lang), style: const TextStyle(color: Tokens.muted, fontSize: 12, decoration: TextDecoration.lineThrough)),
          ]),
        ]))),
    ));
  }
}

/// Salon wall-clock time from the server's ISO string (e.g. 2026-10-27T09:00:00+03:00), never the device's
/// time zone: a customer abroad must still see the salon's time.
String whenLabel(AppController c, String iso) {
  final date = DateTime.parse(iso.substring(0, 10));
  final hm = iso.substring(11, 16);
  final n = DateTime.now();
  final t0 = DateTime(n.year, n.month, n.day);
  final day = date == t0 ? c.t('today') : date == t0.add(const Duration(days: 1)) ? c.t('tomorrow') : '${date.day}/${date.month}';
  return '$day · \u2066$hm\u2069';
}

class BookingsTab extends StatefulWidget {
  const BookingsTab({super.key, required this.c});
  final AppController c;
  @override
  State<BookingsTab> createState() => _BookingsTabState();
}

class _BookingsTabState extends State<BookingsTab> {
  List<Json>? items;
  String? error;

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    try {
      final r = await widget.c.api.bookings();
      if (mounted) setState(() => items = r);
    } on ApiError catch (e) {
      if (mounted) setState(() => error = errKey(e.code));
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.c;
    final t = c.t;
    return Column(children: [
      PhHead(biz: c.biz, title: t('my_bookings')),
      Expanded(child: RefreshIndicator(onRefresh: load, child: ListView(padding: const EdgeInsets.all(14), children: [
        if (error != null) Notice(t(error!), bad: true),
        if (items != null && items!.isEmpty) Padding(padding: const EdgeInsets.all(32), child: Text(t('no_bookings'), textAlign: TextAlign.center, style: const TextStyle(color: Tokens.muted))),
        for (final b in items ?? <Json>[]) SCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text('${b['beneficiary_name']} — ${(b['services'] as List).map((s) => (s as Json)[c.lang == 'en' ? 'name_en' : 'name_ar']).join('، ')}',
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14))),
              Pill(t('st_${b['status']}'), bg: b['status'] == 'booked' ? Brand.of(c.biz).soft : Tokens.surface2,
                  fg: b['status'] == 'booked' ? Brand.of(c.biz).dark : Tokens.muted),
            ]),
            Text('${whenLabel(c, b['starts_at'] as String)} · ${c.catalog!.branches.where((x) => x.id == b['branch_id']).map((x) => x.name(c.lang)).join()}', style: cap),
            if (b['deposit'] != null) Padding(padding: const EdgeInsets.only(top: 4), child: Text(
                t('deposit_line', {'amount': (b['deposit'] as Json)['amount'] as String, 'state': t('dep_${(b['deposit'] as Json)['status']}')}), style: cap)),
            if ((b['pay_url'] ?? '') != '') Align(alignment: AlignmentDirectional.centerEnd, child: FilledButton.icon(
              onPressed: () async {
                try {
                  final r = await c.api.payDeposit(b['id'] as int);
                  await launchUrl(Uri.parse(r['pay_url'] as String), mode: LaunchMode.externalApplication);
                } on ApiError catch (e) {
                  setState(() => error = errKey(e.code));
                }
              },
              icon: const Icon(Icons.credit_card, size: 16), label: Text(t('pay_deposit')))),
            if (b['can_cancel'] == true) Align(alignment: AlignmentDirectional.centerEnd, child: TextButton(
              onPressed: () async {
                try {
                  await c.api.cancel(b['id'] as int);
                  await load();
                } on ApiError catch (e) {
                  setState(() => error = errKey(e.code));
                }
              },
              child: Text(t('cancel'), style: const TextStyle(color: Color(0xFFB93A46))))),
          ]),
        ),
      ]))),
    ]);
  }
}

class AccountTab extends StatelessWidget {
  const AccountTab({super.key, required this.c});
  final AppController c;
  @override
  Widget build(BuildContext context) {
    final t = c.t;
    final me = c.me!;
    return Column(children: [
      PhHead(biz: c.biz, title: t('account'), trailing: TextButton(onPressed: c.toggleLang, child: Text(t('language'), style: const TextStyle(color: Tokens.ink)))),
      Expanded(child: ListView(padding: const EdgeInsets.all(14), children: [
        Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(me.fullName, style: const TextStyle(fontWeight: FontWeight.w700)),
          Text('\u2066+${me.phone}\u2069', style: cap),
        ]))),
        if (me.points != null || me.packages.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text(t('wallet'), style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          if (me.points != null) SCard(
            leading: CircleAvatar(radius: 17, backgroundColor: Brand.of(c.biz).soft, child: Icon(Icons.star_rounded, color: Brand.of(c.biz).dark, size: 20)),
            child: Text(t('points_n').replaceAll('{n}', '${me.points}'), style: small)),
          for (final p in me.packages) SCard(
            leading: CircleAvatar(radius: 17, backgroundColor: Brand.of(c.biz).soft, child: Icon(Icons.card_giftcard, color: Brand.of(c.biz).dark, size: 20)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text((c.lang == 'en' ? p['name_en'] : p['name_ar']) as String, style: small),
              Text(t('sessions_left').replaceAll('{n}', '${p['sessions_left']}').replaceAll('{total}', '${p['sessions_total']}')
                  .replaceAll('{date}', p['expires_on'] as String), style: cap),
            ])),
        ],
        const SizedBox(height: 16),
        Text(t('beneficiaries'), style: const TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        for (final b in me.beneficiaries) SCard(
          leading: CircleAvatar(radius: 17, backgroundColor: Brand.of(c.biz).soft, child: Text((b['full_name'] as String).characters.first, style: TextStyle(color: Brand.of(c.biz).dark, fontWeight: FontWeight.w700))),
          child: Text(b['relation'] == 'self' ? '${b['full_name']} (${t('me')})' : b['full_name'] as String, style: small)),
        Align(alignment: AlignmentDirectional.centerStart, child: OutlinedButton.icon(
          onPressed: () async {
            final name = await askName(context, t('add_child'), t('child_name'));
            if (name != null && name.trim().isNotEmpty) {
              await c.api.addChild({'full_name': name.trim()});
              await c.refreshMe();
            }
          },
          icon: const Icon(Icons.add, size: 18), label: Text(t('add_child')))),
        const SizedBox(height: 24),
        OutlinedButton(onPressed: c.signOut, child: Text(t('logout'))),
      ])),
    ]);
  }
}

Future<String?> askName(BuildContext context, String title, String label) {
  final ctl = TextEditingController();
  return showDialog<String>(context: context, builder: (ctx) => AlertDialog(
    title: Text(title), content: TextField(controller: ctl, autofocus: true, decoration: InputDecoration(labelText: label)),
    actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('✕')), FilledButton(onPressed: () => Navigator.pop(ctx, ctl.text), child: const Text('✓'))],
  ));
}

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

  void startBooking() => setState(() => tab = 1);

  @override
  Widget build(BuildContext context) {
    final c = widget.c;
    final t = c.t;
    final b = Brand.of(c.biz);
    final pages = [
      HomeTab(c: c, onBook: startBooking, key: ValueKey('home$bookingsVersion')),
      BookFlow(c: c, onDone: () => setState(() { bookingsVersion++; tab = 2; })),
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
  final VoidCallback onBook;
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
    return Column(children: [
      PhHead(biz: c.biz, title: cat.salonName, subtitle: t('biz_${c.biz}'),
          trailing: TextButton(onPressed: c.toggleLang, child: Text(t('language'), style: const TextStyle(color: Tokens.ink))),
          child: Padding(padding: const EdgeInsets.only(top: 14), child: Text(t('hello', {'name': c.me!.fullName.split(' ').first}),
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: Tokens.ink)))),
      Expanded(child: ListView(padding: const EdgeInsets.all(14), children: [
        if (next != null) Container(
          padding: const EdgeInsets.all(16), margin: const EdgeInsets.only(bottom: 14),
          decoration: BoxDecoration(color: Tokens.ink, borderRadius: BorderRadius.circular(20)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(t('next_booking'), style: const TextStyle(color: Colors.white70, fontSize: 13)),
            const SizedBox(height: 4),
            Text(whenLabel(c, next!['starts_at'] as String), style: TextStyle(color: Brand.of(c.biz).base, fontSize: 22, fontWeight: FontWeight.w700)),
            Text('${next!['beneficiary_name']} — ${((next!['services'] as List).first as Json)[c.lang == 'en' ? 'name_en' : 'name_ar']}',
                style: const TextStyle(color: Colors.white)),
          ]),
        ),
        FilledButton.icon(key: const Key('book_now'), onPressed: widget.onBook, icon: const Icon(Icons.event_available_outlined), label: Text(t('book_now'))),
        const SizedBox(height: 18),
        Text(t('branches'), style: const TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        if (c.locationDenied) Notice(t('location_off')),
        for (final br in cat.branches) BranchCard(c: c, branch: br),
      ])),
    ]);
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

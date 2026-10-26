import 'package:flutter/material.dart';

import '../api.dart';
import '../l10n.dart';
import '../main.dart';
import '../theme.dart';
import '../ui.dart';
import 'shell.dart';

/// Booking in the design's steps: service → branch (nearest suggested) → time → who → confirm → done.
class BookFlow extends StatefulWidget {
  const BookFlow({super.key, required this.c, required this.onDone});
  final AppController c;
  final VoidCallback onDone;
  @override
  State<BookFlow> createState() => _BookFlowState();
}

class _BookFlowState extends State<BookFlow> {
  int step = 0;
  int? category;
  ServiceItem? service;
  Branch? branch;
  late DateTime day = DateTime.now();
  int? staffId;
  Json? slots;
  String? slot;
  int? who;
  final notes = TextEditingController();
  String? error;
  bool busy = false;
  Json? done;
  String key = UniqueKey().toString();

  AppController get c => widget.c;
  String get dayIso => '${day.year}-${day.month.toString().padLeft(2, '0')}-${day.day.toString().padLeft(2, '0')}';

  List<Branch> branchesFor(ServiceItem s) => c.catalog!.branches.where((b) => b.businessType == s.businessType).toList();

  Future<void> loadSlots() async {
    setState(() { slots = null; slot = null; error = null; });
    try {
      final r = await c.api.slots(branch!.id, service!.id, dayIso, staffId: staffId);
      if (mounted) setState(() => slots = r);
    } on ApiError catch (e) {
      if (mounted) setState(() => error = errKey(e.code));
    }
  }

  Future<void> confirm() async {
    setState(() { busy = true; error = null; });
    try {
      final r = await c.api.book({'branch_id': branch!.id, 'service_id': service!.id, 'starts_at': slot, 'beneficiary_id': who,
        'staff_id': staffId, 'notes': notes.text}, key);
      setState(() => done = r);
    } on ApiError catch (e) {
      setState(() { error = errKey(e.code); if (e.code.startsWith('slot')) { step = 2; loadSlots(); } });
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  void reset() => setState(() { step = 0; service = null; branch = null; staffId = null; slots = null; slot = null; who = null; done = null; error = null; notes.clear(); key = UniqueKey().toString(); });

  @override
  Widget build(BuildContext context) {
    final t = c.t;
    final cat = c.catalog!;
    final titles = [t('step_service'), t('step_branch'), t('step_time'), t('step_who'), t('step_confirm')];
    if (done != null) {
      return Column(children: [
        PhHead(biz: c.biz, title: t('booked_title')),
        Expanded(child: ListView(padding: const EdgeInsets.all(30), children: [
          CircleAvatar(radius: 36, backgroundColor: Brand.of(c.biz).base, child: const Icon(Icons.check, size: 36, color: Tokens.ink)),
          const SizedBox(height: 12),
          Text(t('booked_title'), textAlign: TextAlign.center, style: title18),
          const SizedBox(height: 8),
          Text(t('booked_body', {'who': done!['beneficiary_name'] as String, 'service': service!.name(c.lang),
            'when': whenLabel(c, done!['starts_at'] as String), 'branch': branch!.name(c.lang)}),
              textAlign: TextAlign.center, style: const TextStyle(color: Tokens.muted, height: 1.8)),
          const SizedBox(height: 20),
          FilledButton(onPressed: () { reset(); widget.onDone(); }, child: Text(t('my_bookings'))),
        ])),
      ]);
    }
    final body = <Widget>[Steps(count: 5, at: step, biz: c.biz)];
    switch (step) {
      case 0:
        final types = cat.branches.map((b) => b.businessType).toSet();
        final cats = cat.categories.where((x) => types.contains(x['business_type'])).toList();
        category ??= cats.isNotEmpty ? cats.first['id'] as int : null;
        body.addAll([
          SingleChildScrollView(scrollDirection: Axis.horizontal, child: Row(children: [
            for (final x in cats) Padding(padding: const EdgeInsetsDirectional.only(end: 6), child: DChip(
                label: (c.lang == 'en' && (x['name_en'] as String).isNotEmpty ? x['name_en'] : x['name_ar']) as String,
                on: category == x['id'], onTap: () => setState(() => category = x['id'] as int))),
          ])),
          const SizedBox(height: 10),
          for (final s in cat.services.where((s) => s.category == category)) SCard(
            onTap: () => setState(() {
              service = s;
              final bs = branchesFor(s);
              branch = bs.isEmpty ? null : bs.first; // nearest first (server-sorted)
              step = 1;
            }),
            leading: CircleAvatar(radius: 24, backgroundColor: Brand.of(c.biz).soft, child: Icon(Icons.content_cut, color: Brand.of(c.biz).dark)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(s.name(c.lang), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
              Text('⏱ ${s.minutes} ${t('min')}', style: cap),
              Text(kwd(s.price, c.lang), style: TextStyle(fontWeight: FontWeight.w700, color: Brand.of(c.biz).dark)),
            ]),
          ),
        ]);
      case 1:
        final bs = branchesFor(service!);
        if (c.locationDenied) body.add(Notice(t('location_off')));
        for (final (i, b) in bs.indexed) {
          if (i == 1) body.add(Padding(padding: const EdgeInsets.fromLTRB(0, 8, 0, 6), child: Text(t('other_branches'), style: const TextStyle(fontWeight: FontWeight.w700))));
          body.add(BranchCard(c: c, branch: b, actions: false, selected: branch?.id == b.id,
              onTap: () { setState(() { branch = b; step = 2; staffId = null; }); loadSlots(); }));
        }
      case 2:
        final staff = (slots?['staff'] as List?)?.cast<Json>() ?? [];
        final list = (slots?['slots'] as List?)?.cast<Json>() ?? [];
        body.addAll([
          SingleChildScrollView(scrollDirection: Axis.horizontal, child: Row(children: [
            for (var i = 0; i < 14; i++) Builder(builder: (_) {
              final d = DateTime.now().add(Duration(days: i));
              final on = d.day == day.day && d.month == day.month;
              final label = i == 0 ? t('today') : i == 1 ? t('tomorrow') : '${d.day}/${d.month}';
              return Padding(padding: const EdgeInsetsDirectional.only(end: 6), child: DChip(label: label, on: on, onTap: () { setState(() => day = d); loadSlots(); }));
            }),
          ])),
          const SizedBox(height: 14),
          Text(t('staff'), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
          const SizedBox(height: 6),
          Wrap(spacing: 6, runSpacing: 6, children: [
            DChip(label: t('any_staff'), on: staffId == null, onTap: () { setState(() => staffId = null); loadSlots(); }),
            for (final s in staff) DChip(label: (c.lang == 'en' && (s['name_en'] as String).isNotEmpty ? s['name_en'] : s['name_ar']) as String,
                on: staffId == s['id'], onTap: () { setState(() => staffId = s['id'] as int); loadSlots(); }),
          ]),
          const SizedBox(height: 14),
          Text(t('time'), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
          const SizedBox(height: 6),
          if (slots == null && error == null) const Padding(padding: EdgeInsets.all(20), child: Center(child: CircularProgressIndicator())),
          if (slots != null && list.isEmpty) Notice(t('no_slots')),
          GridView.count(crossAxisCount: 4, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(), mainAxisSpacing: 6, crossAxisSpacing: 6, childAspectRatio: 2.2,
              children: [for (final s in list) DChip(label: s['time'] as String, center: true, on: slot == s['starts_at'],
                  onTap: () => setState(() { slot = s['starts_at'] as String; step = 3; }))]),
        ]);
      case 3:
        for (final b in c.me!.beneficiaries) {
          body.add(SCard(
            selected: who == b['id'], onTap: () => setState(() { who = b['id'] as int; step = 4; }),
            leading: CircleAvatar(radius: 18, backgroundColor: Brand.of(c.biz).soft, child: Text((b['full_name'] as String).characters.first, style: TextStyle(color: Brand.of(c.biz).dark, fontWeight: FontWeight.w700))),
            child: Text(b['relation'] == 'self' ? '${b['full_name']} (${t('me')})' : b['full_name'] as String, style: const TextStyle(fontWeight: FontWeight.w700)),
          ));
        }
        body.add(Align(alignment: AlignmentDirectional.centerStart, child: OutlinedButton.icon(
          onPressed: () async {
            final n = await askName(context, t('add_child'), t('child_name'));
            if (n != null && n.trim().isNotEmpty) { await c.api.addChild({'full_name': n.trim()}); await c.refreshMe(); setState(() {}); }
          }, icon: const Icon(Icons.add, size: 18), label: Text(t('add_child')))));
      default:
        final whoName = c.me!.beneficiaries.firstWhere((b) => b['id'] == who)['full_name'] as String;
        body.addAll([
          SCard(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(service!.name(c.lang), style: const TextStyle(fontWeight: FontWeight.w700)),
            Text(whoName, style: cap),
          ])),
          Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(children: [
            for (final (k, v) in [(t('branch'), branch!.name(c.lang)), (t('when'), whenLabel(c, slot!)),
              (t('pay_at_salon'), kwd((slots?['price'] as String?)?.isNotEmpty == true ? slots!['price'] as String : service!.price, c.lang))])
              Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                Text(k, style: const TextStyle(color: Tokens.muted, fontSize: 14)), Text(v, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14))])),
          ]))),
          const SizedBox(height: 10),
          TextField(controller: notes, decoration: InputDecoration(hintText: t('notes'))),
          const SizedBox(height: 14),
          FilledButton(key: const Key('confirm'), onPressed: busy ? null : confirm, child: Text(t('confirm'))),
        ]);
    }
    if (error != null) body.add(Notice(t(error!), bad: true));
    return Column(children: [
      PhHead(biz: c.biz, title: titles[step], onBack: step == 0 ? null : () => setState(() { step--; error = null; })),
      Expanded(child: ListView(padding: const EdgeInsets.all(14), children: body)),
    ]);
  }
}

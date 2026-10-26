import 'package:flutter/material.dart';

import '../api.dart';
import '../l10n.dart';
import '../main.dart';
import '../theme.dart';
import '../ui.dart';

/// Phone → WhatsApp code → (first time) name + children. Mirrors the design's caLogin.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.c});
  final AppController c;
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final phone = TextEditingController(), code = TextEditingController(), name = TextEditingController();
  final children = <TextEditingController>[];
  String step = 'phone';
  String? error, testCode, regToken;
  bool busy = false, forMe = true;

  AppController get c => widget.c;

  Future<void> run(Future<void> Function() fn) async {
    setState(() { busy = true; error = null; });
    try {
      await fn();
    } on ApiError catch (e) {
      setState(() => error = errKey(e.code));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> sendCode() => run(() async {
        final r = await c.api.requestCode(phone.text, c.lang);
        setState(() { step = 'code'; testCode = r['debug_code'] as String?; code.clear(); });
      });

  Future<void> verify() => run(() async {
        final r = await c.api.verifyCode(phone.text, code.text);
        if (r['new'] == true) {
          setState(() { step = 'register'; regToken = r['registration_token'] as String; });
        } else {
          await c.signedIn(r['token'] as String);
        }
      });

  Future<void> register() => run(() async {
        final r = await c.api.register({
          'registration_token': regToken, 'full_name': name.text.trim(), 'lang': c.lang, 'self_service': forMe,
          'children': [for (final ch in children) if (ch.text.trim().isNotEmpty) {'full_name': ch.text.trim()}],
        });
        await c.signedIn(r['token'] as String);
      });

  @override
  Widget build(BuildContext context) {
    final cat = c.catalog!;
    final t = c.t;
    Widget field(String label, TextEditingController ctl, {bool ltr = false, TextInputType? kb, Key? key}) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, style: const TextStyle(fontSize: 13, color: Tokens.muted, fontWeight: FontWeight.w500)),
          const SizedBox(height: 4),
          TextField(key: key, controller: ctl, keyboardType: kb, textDirection: ltr ? TextDirection.ltr : null),
        ]));
    final body = switch (step) {
      'phone' => [
          Text(t('login_title'), style: const TextStyle(fontSize: 25, fontWeight: FontWeight.w700)),
          Text(t('login_sub'), style: const TextStyle(fontSize: 13, color: Tokens.muted)),
          const SizedBox(height: 16),
          field(t('phone'), phone, ltr: true, kb: TextInputType.phone, key: const Key('phone')),
          FilledButton(key: const Key('send'), onPressed: busy ? null : sendCode, child: Text(t('send_code'))),
        ],
      'code' => [
          Text(t('code_title'), style: const TextStyle(fontSize: 25, fontWeight: FontWeight.w700)),
          Text(t('code_sub', {'phone': '\u2066${phone.text}\u2069'}), style: const TextStyle(fontSize: 13, color: Tokens.muted)),
          if (testCode != null) Notice(t('test_code', {'code': testCode!})),
          const SizedBox(height: 12),
          field(t('code'), code, ltr: true, kb: TextInputType.number, key: const Key('code')),
          FilledButton(key: const Key('verify'), onPressed: busy ? null : verify, child: Text(t('verify'))),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            TextButton(onPressed: () => setState(() => step = 'phone'), child: Text(t('change_phone'))),
            TextButton(onPressed: busy ? null : sendCode, child: Text(t('resend'))),
          ]),
        ],
      _ => [
          Text(t('register_title'), style: const TextStyle(fontSize: 25, fontWeight: FontWeight.w700)),
          Text(t('register_sub'), style: const TextStyle(fontSize: 13, color: Tokens.muted)),
          const SizedBox(height: 16),
          field(t('your_name'), name, key: const Key('name')),
          SwitchListTile(contentPadding: EdgeInsets.zero, value: forMe, onChanged: (v) => setState(() => forMe = v),
              title: Text(t('for_me'), style: small), activeTrackColor: Brand.of(c.biz).base),
          if (c.biz == 'kids' || children.isNotEmpty || !forMe) ...[
            Text(t('children'), style: const TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            for (final (i, ch) in children.indexed) field('${t('child_name')} ${i + 1}', ch, key: Key('child$i')),
            Align(alignment: AlignmentDirectional.centerStart, child: OutlinedButton.icon(
                onPressed: () => setState(() => children.add(TextEditingController())), icon: const Icon(Icons.add, size: 18), label: Text(t('add_child')))),
            const SizedBox(height: 12),
          ],
          FilledButton(key: const Key('register'), onPressed: busy ? null : register, child: Text(t('create_account'))),
        ],
    };
    return Scaffold(
      body: Column(children: [
        PhHead(biz: c.biz, title: cat.salonName, subtitle: t('biz_${c.biz}'),
            trailing: TextButton(onPressed: c.toggleLang, child: Text(t('language'), style: const TextStyle(color: Tokens.ink)))),
        Expanded(child: ListView(padding: const EdgeInsets.all(18), children: [
          ...body,
          if (error != null) Notice(t(error!), bad: true),
        ])),
      ]),
    );
  }
}

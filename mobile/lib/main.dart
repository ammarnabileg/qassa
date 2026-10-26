import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

import 'api.dart';
import 'config.dart';
import 'l10n.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  // Web (PWA): each company has its own host, so the salon comes from the address bar.
  // Store app (D-001 picker): ?salon=<slug> link or the last chosen salon.
  final fromUrl = Uri.base.queryParameters['salon'];
  runApp(QassaApp(api: Api(), prefs: prefs, byHost: kIsWeb, initialSlug: fromUrl ?? prefs.getString('salon')));
}

class QassaApp extends StatefulWidget {
  const QassaApp({super.key, required this.api, required this.prefs, this.initialSlug, this.byHost = false});
  final Api api;
  final SharedPreferences prefs;
  final String? initialSlug;
  final bool byHost;
  @override
  State<QassaApp> createState() => _QassaAppState();
}

class _QassaAppState extends State<QassaApp> {
  late String lang = widget.prefs.getString('lang') ?? 'ar';
  Salon? salon;
  String? error;
  bool loading = false;

  @override
  void initState() {
    super.initState();
    start();
  }

  Future<void> start() async {
    if (widget.byHost) {
      setState(() => loading = true);
      try {
        final s = await widget.api.salonForHost();
        setState(() { salon = s; loading = false; });
        return;
      } on ApiError catch (e) {
        setState(() => loading = false);
        if (e.code != 'salon_not_found') { setState(() => error = e.code == 'network' ? 'err_network' : 'err_unknown'); return; }
      }
    }
    if (widget.initialSlug != null) await open(widget.initialSlug!);
  }

  Future<void> open(String slug) async {
    setState(() { loading = true; error = null; });
    try {
      final s = await widget.api.salon(slug.trim().toLowerCase());
      await widget.prefs.setString('salon', s.slug);
      setState(() => salon = s);
    } on ApiError catch (e) {
      setState(() => error = e.code == 'salon_not_found' || e.code == 'network' ? 'err_${e.code}' : 'err_unknown');
    } finally {
      setState(() => loading = false);
    }
  }

  void changeSalon() {
    widget.prefs.remove('salon');
    setState(() => salon = null);
  }

  void toggleLang() {
    setState(() => lang = lang == 'ar' ? 'en' : 'ar');
    widget.prefs.setString('lang', lang);
  }

  @override
  Widget build(BuildContext context) {
    String t(String k) => tr(lang, k);
    return MaterialApp(
      title: t('app_name'),
      debugShowCheckedModeBanner: Config.channel != 'release',
      locale: Locale(lang),
      supportedLocales: const [Locale('ar'), Locale('en')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      theme: themeFor(salon?.businessType, Brightness.light),
      darkTheme: themeFor(salon?.businessType, Brightness.dark),
      home: salon == null
          ? PickerScreen(t: t, loading: loading, error: error, onSubmit: open, onLang: toggleLang)
          : SalonScreen(t: t, lang: lang, salon: salon!, onChange: salon!.locked ? null : changeSalon, onLang: toggleLang),
    );
  }
}

class PickerScreen extends StatefulWidget {
  const PickerScreen({super.key, required this.t, required this.loading, required this.error, required this.onSubmit, required this.onLang});
  final String Function(String) t;
  final bool loading;
  final String? error;
  final void Function(String) onSubmit;
  final VoidCallback onLang;
  @override
  State<PickerScreen> createState() => _PickerScreenState();
}

class _PickerScreenState extends State<PickerScreen> {
  final ctrl = TextEditingController();
  @override
  Widget build(BuildContext context) {
    final t = widget.t;
    void submit() { if (ctrl.text.trim().isNotEmpty && !widget.loading) widget.onSubmit(ctrl.text); }
    return Scaffold(
      body: Container(
        // the design's login background: brand-soft glow on the page colour
        decoration: BoxDecoration(gradient: RadialGradient(center: const Alignment(-0.6, -0.8), radius: 0.9,
            colors: [Brand.kids.soft, Tokens.bg])),
        child: SafeArea(child: Center(child: SingleChildScrollView(padding: const EdgeInsets.all(16), child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 400),
          child: Card(child: Padding(padding: const EdgeInsets.all(28), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(children: [
              const LogoMark(biz: 'kids'),
              const SizedBox(width: 10),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(t('app_name'), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                Text(t('app_tagline'), style: const TextStyle(fontSize: 11, color: Tokens.muted)),
              ])),
              TextButton(onPressed: widget.onLang, child: Text(t('language'))),
            ]),
            const SizedBox(height: 20),
            Text(t('pick_title'), style: const TextStyle(fontSize: 25, fontWeight: FontWeight.w700, letterSpacing: -.5)),
            Text(t('pick_sub'), style: const TextStyle(fontSize: 13, color: Tokens.muted)),
            const SizedBox(height: 16),
            Text(t('pick_hint'), style: const TextStyle(fontSize: 13, color: Tokens.muted, fontWeight: FontWeight.w500)),
            const SizedBox(height: 4),
            TextField(key: const Key('slug'), controller: ctrl, textDirection: TextDirection.ltr, onSubmitted: (_) => submit()),
            if (widget.error != null) Container(
              margin: const EdgeInsets.only(top: 12), padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: const Color(0xFFFCECEF), borderRadius: BorderRadius.circular(Tokens.rMd)),
              child: Text(t(widget.error!), style: const TextStyle(color: Color(0xFFA52E3B), fontSize: 13))),
            const SizedBox(height: 16),
            FilledButton(onPressed: widget.loading ? null : submit,
                child: widget.loading ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : Text(t('pick_go'))),
            const SizedBox(height: 16),
            Text('${t('version')} \u2066${Config.version} (${Config.channel})\u2069', textAlign: TextAlign.center, style: const TextStyle(fontSize: 11, color: Tokens.muted)),
          ]))),
        )))),
      ),
    );
  }
}

class SalonScreen extends StatelessWidget {
  const SalonScreen({super.key, required this.t, required this.lang, required this.salon, required this.onChange, required this.onLang});
  final String Function(String) t;
  final String lang;
  final Salon salon;
  final VoidCallback? onChange;
  final VoidCallback onLang;

  /// Kuwait numbers: 8 digits → +965.
  static String intl(String phone) {
    final d = phone.replaceAll(RegExp(r'\D'), '');
    return d.length == 8 ? '965$d' : d;
  }

  @override
  Widget build(BuildContext context) {
    final b = Brand.of(salon.businessType);
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 16,
        title: Row(children: [
          LogoMark(biz: salon.businessType, size: 36),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(salon.name, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            Text(t('biz_${salon.businessType}'), style: const TextStyle(fontSize: 11, color: Tokens.muted)),
          ])),
        ]),
        actions: [
          TextButton(onPressed: onLang, child: Text(t('language'))),
          if (onChange != null) IconButton(tooltip: t('change_salon'), onPressed: onChange, icon: const Icon(Icons.swap_horiz)),
          const SizedBox(width: 4),
        ],
      ),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(color: Tokens.infoBg, borderRadius: BorderRadius.circular(Tokens.rMd)),
          child: Row(children: [
            const Icon(Icons.info_outline, size: 20, color: Tokens.infoInk),
            const SizedBox(width: 10),
            Expanded(child: Text(t('booking_soon'), style: const TextStyle(color: Tokens.infoInk, fontSize: 13))),
          ]),
        ),
        const SizedBox(height: 18),
        Text(t('branches'), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
        const SizedBox(height: 10),
        Card(child: Padding(padding: const EdgeInsets.symmetric(horizontal: 18), child: Column(children: [
          for (final (i, br) in salon.branches.indexed) Container(
            padding: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(border: i == salon.branches.length - 1 ? null : const Border(bottom: BorderSide(color: Tokens.line))),
            child: Row(children: [
              CircleAvatar(radius: 17, backgroundColor: b.soft, child: Icon(Icons.storefront_outlined, size: 18, color: b.dark)),
              const SizedBox(width: 10),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(br.name(lang), style: const TextStyle(fontWeight: FontWeight.w700)),
                if (br.address.isNotEmpty) Text(br.address, style: const TextStyle(fontSize: 12, color: Tokens.muted)),
              ])),
              if (br.phone.isNotEmpty) ...[
                OutlinedButton.icon(onPressed: () => launchUrl(Uri.parse('tel:+${intl(br.phone)}')), icon: const Icon(Icons.call_outlined, size: 16), label: Text(t('call'))),
                const SizedBox(width: 6),
                OutlinedButton.icon(onPressed: () => launchUrl(Uri.parse('https://wa.me/${intl(br.phone)}'), mode: LaunchMode.externalApplication),
                    icon: const Icon(Icons.chat_outlined, size: 16), label: Text(t('whatsapp'))),
              ],
            ]),
          ),
        ]))),
      ]),
    );
  }
}

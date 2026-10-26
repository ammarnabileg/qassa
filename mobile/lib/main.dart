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
      appBar: AppBar(title: Text(t('app_name')), actions: [TextButton(onPressed: widget.onLang, child: Text(t('language')))]),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: ListView(padding: const EdgeInsets.all(24), shrinkWrap: true, children: [
            Text(t('pick_title'), style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 16),
            TextField(key: const Key('slug'), controller: ctrl, decoration: InputDecoration(labelText: t('pick_hint'), border: const OutlineInputBorder()), onSubmitted: (_) => submit()),
            if (widget.error != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(t(widget.error!), style: TextStyle(color: Theme.of(context).colorScheme.error))),
            const SizedBox(height: 16),
            FilledButton(onPressed: widget.loading ? null : submit, child: widget.loading ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2)) : Text(t('pick_go'))),
            const SizedBox(height: 32),
            Text('${t('version')} ${Config.version} (${Config.channel})', textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodySmall),
          ]),
        ),
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
    return Scaffold(
      appBar: AppBar(title: Text(salon.name), actions: [
        TextButton(onPressed: onLang, child: Text(t('language'))),
        if (onChange != null) IconButton(tooltip: t('change_salon'), onPressed: onChange, icon: const Icon(Icons.swap_horiz)),
      ]),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Card(child: Padding(padding: const EdgeInsets.all(16), child: Text(t('booking_soon')))),
        const SizedBox(height: 8),
        Text(t('branches'), style: Theme.of(context).textTheme.titleMedium),
        for (final b in salon.branches)
          Card(
            child: ListTile(
              title: Text(b.name(lang)),
              subtitle: b.address.isEmpty ? null : Text(b.address),
              trailing: b.phone.isEmpty
                  ? null
                  : Wrap(children: [
                      IconButton(tooltip: t('call'), icon: const Icon(Icons.call), onPressed: () => launchUrl(Uri.parse('tel:+${intl(b.phone)}'))),
                      IconButton(tooltip: t('whatsapp'), icon: const Icon(Icons.chat), onPressed: () => launchUrl(Uri.parse('https://wa.me/${intl(b.phone)}'), mode: LaunchMode.externalApplication)),
                    ]),
            ),
          ),
      ]),
    );
  }
}

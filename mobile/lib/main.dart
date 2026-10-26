import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'config.dart';
import 'l10n.dart';
import 'screens/login.dart';
import 'screens/shell.dart';
import 'theme.dart';
import 'ui.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  // On a company's domain the host names the salon. Elsewhere (store app, local testing) ?salon=<slug>.
  final slug = Uri.base.queryParameters['salon'];
  runApp(QassaApp(controller: AppController(api: Api(salonSlug: slug), prefs: prefs)));
}

/// App state: language, the salon's catalog, the signed-in customer.
class AppController extends ChangeNotifier {
  AppController({required this.api, required this.prefs, this.locate = true});
  final Api api;
  final SharedPreferences prefs;
  final bool locate;
  late String lang = prefs.getString('lang') ?? 'ar';
  Catalog? catalog;
  Me? me;
  String? fatal; // salon_not_found / network …
  bool booting = true;
  bool locationDenied = false;
  double? lat, lng;

  String t(String key, [Map<String, String> args = const {}]) => tr(lang, key, args);
  String get biz => catalog?.businessType ?? 'kids';
  String _tokenKey() => 'token:${api.salonSlug ?? Uri.base.host}';

  Future<void> boot() async {
    booting = true;
    fatal = null;
    notifyListeners();
    try {
      catalog = await api.catalog();
      api.token = prefs.getString(_tokenKey());
      if (api.token != null) {
        try {
          me = await api.me();
        } on ApiError catch (e) {
          if (e.code != 'auth') rethrow;
          await signOut(notify: false);
        }
      }
    } on ApiError catch (e) {
      fatal = e.code == 'salon_not_found' ? 'no_salon' : (e.code == 'network' ? 'err_network' : 'err_unknown');
    }
    booting = false;
    notifyListeners();
    if (me != null) findNearest();
  }

  /// Ask for the location once; the server sorts branches nearest first and marks the recommended one.
  Future<void> findNearest() async {
    if (!locate || lat != null) return;
    try {
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) perm = await Geolocator.requestPermission();
      if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) {
        locationDenied = true;
        notifyListeners();
        return;
      }
      final pos = await Geolocator.getCurrentPosition(locationSettings: const LocationSettings(timeLimit: Duration(seconds: 10)));
      lat = pos.latitude;
      lng = pos.longitude;
      catalog = await api.catalog(lat: lat, lng: lng);
      notifyListeners();
    } catch (_) {
      locationDenied = true;
      notifyListeners();
    }
  }

  Future<void> signedIn(String token) async {
    api.token = token;
    await prefs.setString(_tokenKey(), token);
    me = await api.me();
    notifyListeners();
    findNearest();
  }

  Future<void> refreshMe() async {
    me = await api.me();
    notifyListeners();
  }

  Future<void> signOut({bool notify = true}) async {
    api.token = null;
    me = null;
    await prefs.remove(_tokenKey());
    if (notify) notifyListeners();
  }

  void toggleLang() {
    lang = lang == 'ar' ? 'en' : 'ar';
    prefs.setString('lang', lang);
    notifyListeners();
  }
}

class QassaApp extends StatefulWidget {
  const QassaApp({super.key, required this.controller});
  final AppController controller;
  @override
  State<QassaApp> createState() => _QassaAppState();
}

class _QassaAppState extends State<QassaApp> {
  @override
  void initState() {
    super.initState();
    widget.controller.boot();
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    return ListenableBuilder(
      listenable: c,
      builder: (context, _) => MaterialApp(
        title: c.catalog?.salonName ?? c.t('app_name'),
        debugShowCheckedModeBanner: false,
        locale: Locale(c.lang),
        supportedLocales: const [Locale('ar'), Locale('en')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        theme: themeFor(c.biz, Brightness.light),
        home: c.booting
            ? const Scaffold(body: Center(child: CircularProgressIndicator()))
            : c.fatal != null
                ? FatalScreen(c: c)
                : c.me == null
                    ? LoginScreen(c: c)
                    : Shell(c: c),
      ),
    );
  }
}

class FatalScreen extends StatelessWidget {
  const FatalScreen({super.key, required this.c});
  final AppController c;
  @override
  Widget build(BuildContext context) {
    final noSalon = c.fatal == 'no_salon';
    return Scaffold(
      body: Center(child: Padding(padding: const EdgeInsets.all(24), child: Column(mainAxisSize: MainAxisSize.min, children: [
        const LogoMark(biz: 'kids', size: 56),
        const SizedBox(height: 16),
        Text(noSalon ? c.t('no_salon_title') : c.t(c.fatal!), style: title18, textAlign: TextAlign.center),
        if (noSalon) ...[const SizedBox(height: 8), Text(c.t('no_salon_body'), style: const TextStyle(color: Tokens.muted), textAlign: TextAlign.center)],
        if (!noSalon) ...[const SizedBox(height: 16), OutlinedButton(onPressed: c.boot, child: Text(c.t('retry')))],
        const SizedBox(height: 24),
        Text('${c.t('version')} \u2066${Config.version}\u2069', style: cap),
      ]))),
    );
  }
}

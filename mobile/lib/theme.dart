import 'package:flutter/material.dart';

/// Tokens copied from the approved design (reference/salon-pos-demo/assets/css/base.css + themes.css).
class Tokens {
  static const bg = Color(0xFFF6F8F6), surface = Color(0xFFFFFFFF), surface2 = Color(0xFFF0F4F1);
  static const ink = Color(0xFF081510), ink2 = Color(0xFF1B2A24), muted = Color(0xFF5C6862);
  static const line = Color(0xFFDDE5E0), lineStrong = Color(0xFFCCD7D0), sun = Color(0xFFFFC83D);
  static const infoBg = Color(0xFFEEF3FF), infoInk = Color(0xFF2457C6);
  static const rMd = 12.0, rLg = 18.0;
}

/// brand, brand-700, brand-soft per business type (kids default).
class Brand {
  const Brand(this.base, this.dark, this.soft);
  final Color base, dark, soft;
  static const kids = Brand(Color(0xFF0CD273), Color(0xFF067C44), Color(0xFFEAFBF2));
  static const men = Brand(Color(0xFFC9A24B), Color(0xFF7A5A12), Color(0xFFF7F0E1));
  static const women = Brand(Color(0xFFEC6F9A), Color(0xFFB02A5B), Color(0xFFFDECF2));
  static Brand of(String? biz) => switch (biz) { 'men' => men, 'women' => women, _ => kids };
}

ThemeData themeFor(String? businessType, Brightness brightness) {
  final b = Brand.of(businessType);
  final base = ThemeData(useMaterial3: true, fontFamily: 'Alexandria', brightness: Brightness.light);
  return base.copyWith(
    scaffoldBackgroundColor: Tokens.bg,
    colorScheme: ColorScheme.light(primary: Tokens.ink, onPrimary: Tokens.surface, secondary: b.base, surface: Tokens.surface,
        onSurface: Tokens.ink, error: const Color(0xFFB93A46)),
    textTheme: base.textTheme.apply(bodyColor: Tokens.ink, displayColor: Tokens.ink),
    appBarTheme: const AppBarTheme(backgroundColor: Tokens.surface, foregroundColor: Tokens.ink, elevation: 0, scrolledUnderElevation: 0,
        shape: Border(bottom: BorderSide(color: Tokens.line))),
    cardTheme: CardThemeData(color: Tokens.surface, elevation: 0, margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Tokens.rLg), side: const BorderSide(color: Tokens.line))),
    inputDecorationTheme: InputDecorationTheme(filled: true, fillColor: Tokens.surface, contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(Tokens.rMd), borderSide: const BorderSide(color: Tokens.lineStrong)),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(Tokens.rMd), borderSide: BorderSide(color: b.dark, width: 2)),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(Tokens.rMd))),
    filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(backgroundColor: Tokens.ink, foregroundColor: Tokens.surface,
        minimumSize: const Size.fromHeight(52), textStyle: const TextStyle(fontFamily: 'Alexandria', fontSize: 17, fontWeight: FontWeight.w600),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Tokens.rMd)))),
    outlinedButtonTheme: OutlinedButtonThemeData(style: OutlinedButton.styleFrom(foregroundColor: Tokens.ink, side: const BorderSide(color: Tokens.lineStrong),
        textStyle: const TextStyle(fontFamily: 'Alexandria', fontWeight: FontWeight.w600, fontSize: 13),
        padding: const EdgeInsets.symmetric(horizontal: 10), minimumSize: const Size(0, 34),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Tokens.rMd)))),
    textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(foregroundColor: Tokens.ink,
        textStyle: const TextStyle(fontFamily: 'Alexandria', fontWeight: FontWeight.w600))),
  );
}

/// The design's logo: scissors on the brand colour with a per-type accent (crown / moustache / bow).
class LogoMark extends StatelessWidget {
  const LogoMark({super.key, required this.biz, this.size = 40});
  final String? biz;
  final double size;
  @override
  Widget build(BuildContext context) => CustomPaint(size: Size.square(size), painter: _LogoPainter(biz));
}

class _LogoPainter extends CustomPainter {
  _LogoPainter(this.biz);
  final String? biz;
  @override
  void paint(Canvas c, Size s) {
    c.scale(s.width / 64);
    c.drawRRect(RRect.fromRectAndRadius(const Rect.fromLTWH(0, 0, 64, 64), const Radius.circular(18)), Paint()..color = Brand.of(biz).base);
    final fill = Paint()..style = PaintingStyle.fill;
    if (biz == 'kids' || biz == null) {
      c.drawPath(Path()..moveTo(20, 15)..lineTo(24, 10)..lineTo(28, 15)..lineTo(32, 10)..lineTo(36, 15)..lineTo(40, 10)..lineTo(44, 15)
        ..lineTo(44, 19)..lineTo(20, 19)..close(), fill..color = Tokens.sun);
    } else if (biz == 'men') {
      c.drawPath(Path()..moveTo(32, 17)..cubicTo(29, 12, 23, 12, 20, 16)..cubicTo(23, 15, 26, 16, 28, 18)..cubicTo(30, 19, 32, 18, 32, 17)
        ..moveTo(32, 17)..cubicTo(35, 12, 41, 12, 44, 16)..cubicTo(41, 15, 38, 16, 36, 18)..cubicTo(34, 19, 32, 18, 32, 17), fill..color = Tokens.ink);
    } else {
      c.drawPath(Path()..moveTo(32, 15)..lineTo(23, 9)..lineTo(23, 21)..close()..moveTo(32, 15)..lineTo(41, 9)..lineTo(41, 21)..close(), fill..color = Colors.white);
      c.drawCircle(const Offset(32, 15), 2.6, fill..color = Colors.white);
    }
    final stroke = Paint()..style = PaintingStyle.stroke..strokeWidth = 4..strokeCap = StrokeCap.round..color = Tokens.ink;
    c.drawCircle(const Offset(23, 46), 6, stroke);
    c.drawCircle(const Offset(41, 46), 6, stroke);
    c.drawLine(const Offset(27, 41), const Offset(41, 24), stroke);
    c.drawLine(const Offset(37, 41), const Offset(23, 24), stroke);
  }

  @override
  bool shouldRepaint(_LogoPainter old) => old.biz != biz;
}

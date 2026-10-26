import 'package:flutter/material.dart';

import 'theme.dart';

/// Widgets reproducing the approved customer-app design (reference/salon-pos-demo/assets/css/customer-app.css).

/// `.ph-head`: brand-coloured header with the logo.
class PhHead extends StatelessWidget {
  const PhHead({super.key, required this.biz, required this.title, this.subtitle, this.trailing, this.child, this.onBack});
  final String biz, title;
  final String? subtitle;
  final Widget? trailing, child;
  final VoidCallback? onBack;
  @override
  Widget build(BuildContext context) {
    final b = Brand.of(biz);
    return Container(
      color: b.base,
      padding: EdgeInsets.fromLTRB(18, MediaQuery.paddingOf(context).top + 14, 18, child == null ? 16 : 22),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          if (onBack != null) ...[
            Material(color: Colors.white.withValues(alpha: .4), borderRadius: BorderRadius.circular(Tokens.rMd),
                child: InkWell(borderRadius: BorderRadius.circular(Tokens.rMd), onTap: onBack,
                    child: const Padding(padding: EdgeInsets.all(6), child: Icon(Icons.arrow_forward, size: 20, color: Tokens.ink)))),
            const SizedBox(width: 10),
          ] else ...[LogoMark(biz: biz, size: 38), const SizedBox(width: 10)],
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Tokens.ink)),
            if (subtitle != null) Text(subtitle!, style: TextStyle(fontSize: 11, color: b.dark)),
          ])),
          ?trailing,
        ]),
        ?child,
      ]),
    );
  }
}

/// `.scard`: tappable row card.
class SCard extends StatelessWidget {
  const SCard({super.key, required this.child, this.onTap, this.selected = false, this.leading});
  final Widget child;
  final Widget? leading;
  final VoidCallback? onTap;
  final bool selected;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Material(
          color: Tokens.surface,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16),
              side: BorderSide(color: selected ? Tokens.ink : Tokens.line, width: selected ? 2 : 1)),
          child: InkWell(
            borderRadius: BorderRadius.circular(16), onTap: onTap,
            child: Padding(padding: const EdgeInsets.all(10), child: Row(children: [
              if (leading != null) ...[leading!, const SizedBox(width: 12)],
              Expanded(child: child),
            ])),
          ),
        ),
      );
}

/// `.chip` / `.chip.on`
class DChip extends StatelessWidget {
  const DChip({super.key, required this.label, required this.on, this.onTap, this.center = false});
  final String label;
  final bool on, center;
  final VoidCallback? onTap;
  @override
  Widget build(BuildContext context) => Material(
        color: on ? Tokens.ink : Tokens.surface,
        shape: StadiumBorder(side: BorderSide(color: on ? Tokens.ink : Tokens.lineStrong)),
        child: InkWell(customBorder: const StadiumBorder(), onTap: onTap,
            child: Padding(padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
                child: Text(label, textAlign: center ? TextAlign.center : null,
                    style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: on ? Tokens.surface : Tokens.ink)))),
      );
}

/// `.steps`: progress bar of the booking flow.
class Steps extends StatelessWidget {
  const Steps({super.key, required this.count, required this.at, required this.biz});
  final int count, at;
  final String biz;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Row(children: [
          for (var i = 0; i < count; i++) ...[
            Expanded(child: Container(height: 4, decoration: BoxDecoration(color: i <= at ? Brand.of(biz).base : Tokens.line, borderRadius: BorderRadius.circular(99)))),
            if (i < count - 1) const SizedBox(width: 4),
          ],
        ]),
      );
}

class Pill extends StatelessWidget {
  const Pill(this.text, {super.key, this.bg = Tokens.surface2, this.fg = Tokens.muted});
  final String text;
  final Color bg, fg;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 1),
        decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(99)),
        child: Text(text, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: fg)),
      );
}

class Notice extends StatelessWidget {
  const Notice(this.text, {super.key, this.bad = false});
  final String text;
  final bool bad;
  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.symmetric(vertical: 8), padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(color: bad ? const Color(0xFFFCECEF) : const Color(0xFFFFF5DA), borderRadius: BorderRadius.circular(Tokens.rMd)),
        child: Text(text, style: TextStyle(fontSize: 13, color: bad ? const Color(0xFFA52E3B) : const Color(0xFF8B5A08))),
      );
}

const title18 = TextStyle(fontSize: 18, fontWeight: FontWeight.w700);
const small = TextStyle(fontSize: 13);
const cap = TextStyle(fontSize: 12, color: Tokens.muted);

String kwd(String v, String lang) {
  final parts = v.split('.');
  final i = parts[0].replaceAllMapped(RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => ',');
  return '$i.${(parts.length > 1 ? parts[1] : '000').padRight(3, '0')} ${lang == 'ar' ? 'د.ك' : 'KWD'}';
}

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qassa_app/api.dart';
import 'package:qassa_app/l10n.dart';
import 'package:qassa_app/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

final salonJson = {
  'slug': 'my-kids', 'name': 'My Kids', 'business_type': 'kids',
  'branches': [{'id': 1, 'name_ar': 'حولي', 'name_en': 'Hawalli', 'business_type': 'kids', 'address': '', 'phone': '55551234'}],
};

Api fakeApi() => Api(baseUrl: 'http://x', client: MockClient((req) async {
      if (req.url.path.endsWith('/my-kids')) return http.Response.bytes(utf8.encode(jsonEncode(salonJson)), 200);
      return http.Response(jsonEncode({'error': {'code': 'salon_not_found'}}), 404);
    }));

void main() {
  test('Arabic and English have the same keys', () {
    expect(strings['ar']!.keys.toSet(), strings['en']!.keys.toSet());
  });

  test('Kuwait phone gets 965 for wa.me', () {
    expect(SalonScreen.intl('5555 1234'), '96555551234');
    expect(SalonScreen.intl('+96555551234'), '96555551234');
  });

  testWidgets('on a company host the salon opens directly and cannot be changed', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final api = Api(baseUrl: 'http://x', client: MockClient((req) async {
      if (req.url.path == '/api/v1/public/salon') {
        return http.Response.bytes(utf8.encode(jsonEncode({...salonJson, 'locked': true})), 200);
      }
      return http.Response('{}', 500);
    }));
    await tester.pumpWidget(QassaApp(api: api, prefs: prefs, byHost: true));
    await tester.pumpAndSettle();
    expect(find.text('حولي'), findsOneWidget);
    expect(find.byIcon(Icons.swap_horiz), findsNothing);
  });

  testWidgets('on the platform host (no company) the picker is shown', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    await tester.pumpWidget(QassaApp(api: fakeApi(), prefs: prefs, byHost: true));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('slug')), findsOneWidget);
  });

  testWidgets('unknown salon shows translated error; known salon shows branches; choice persists', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    await tester.pumpWidget(QassaApp(api: fakeApi(), prefs: prefs));
    expect(Directionality.of(tester.element(find.byType(TextField))), TextDirection.rtl);

    await tester.enterText(find.byKey(const Key('slug')), 'nope');
    await tester.tap(find.byType(FilledButton));
    await tester.pumpAndSettle();
    expect(find.text(tr('ar', 'err_salon_not_found')), findsOneWidget);

    await tester.enterText(find.byKey(const Key('slug')), 'My-Kids ');
    await tester.tap(find.byType(FilledButton));
    await tester.pumpAndSettle();
    expect(find.text('حولي'), findsOneWidget);
    expect(prefs.getString('salon'), 'my-kids');

    await tester.tap(find.text('English'));
    await tester.pumpAndSettle();
    expect(find.text('Hawalli'), findsOneWidget);
    expect(Directionality.of(tester.element(find.text('Hawalli'))), TextDirection.ltr);
  });
}


import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qassa_app/api.dart';
import 'package:qassa_app/l10n.dart';
import 'package:qassa_app/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

final catalogJson = {
  'salon': {'name': 'My Kids', 'business_type': 'kids'},
  'branches': [
    {'id': 2, 'name_ar': 'الجهراء', 'name_en': 'Jahra', 'business_type': 'kids', 'address': '', 'phone': '', 'opens_at': '10:00', 'closes_at': '22:00', 'distance_km': 1.2, 'recommended': true},
    {'id': 1, 'name_ar': 'حولي', 'name_en': 'Hawalli', 'business_type': 'kids', 'address': '', 'phone': '55551234', 'opens_at': '10:00', 'closes_at': '22:00', 'distance_km': 30.5},
  ],
  'categories': [{'id': 1, 'name_ar': 'قصات', 'name_en': 'Cuts', 'business_type': 'kids'}],
  'services': [{'id': 7, 'category': 1, 'business_type': 'kids', 'name_ar': 'قص شعر', 'name_en': 'Haircut', 'duration_minutes': 30, 'price': '4.500'}],
};
final meJson = {'id': 1, 'full_name': 'أم سارة', 'phone': '96555550001', 'preferred_language': 'ar', 'beneficiaries': [
  {'id': 11, 'full_name': 'سارة', 'relation': 'child', 'birth_date': null, 'gender': ''}]};

http.Response ok(Object body, [int status = 200]) => http.Response.bytes(utf8.encode(jsonEncode(body)), status);

/// A fake backend that records what the app sends.
class Fake {
  final calls = <String>[];
  bool salonExists = true;
  Api api() => Api(baseUrl: 'http://x', client: MockClient((req) async {
        final p = req.url.path.replaceFirst('/api/v1/app', '');
        calls.add('${req.method} $p');
        if (!salonExists) return ok({'error': {'code': 'salon_not_found'}}, 404);
        final authed = req.headers['Authorization'] == 'Customer T1';
        switch ('${req.method} $p') {
          case 'GET /catalog': return ok(catalogJson);
          case 'POST /otp/request': return ok({'sent': true, 'channel': 'console', 'expires_in': 300, 'debug_code': '123456'});
          case 'POST /otp/verify':
            final code = (jsonDecode(req.body) as Map)['code'];
            return code == '123456' ? ok({'new': true, 'registration_token': 'R'}) : ok({'error': {'code': 'otp_invalid'}}, 422);
          case 'POST /register': return ok({'token': 'T1', 'me': meJson}, 201);
          case 'GET /me': return authed ? ok(meJson) : ok({}, 401);
          case 'GET /bookings': return ok([]);
        }
        return ok({'error': {'code': 'unknown'}}, 500);
      }));
}

Future<AppController> start(WidgetTester tester, Fake fake) async {
  SharedPreferences.setMockInitialValues({});
  final c = AppController(api: fake.api(), prefs: await SharedPreferences.getInstance(), locate: false);
  await tester.pumpWidget(QassaApp(controller: c));
  await tester.pumpAndSettle();
  return c;
}

void main() {
  test('Arabic and English have the same keys', () {
    expect(strings['ar']!.keys.toSet(), strings['en']!.keys.toSet());
  });

  testWidgets('without a salon there is no picker — only a message to open the salon link', (tester) async {
    await start(tester, Fake()..salonExists = false);
    expect(find.text(tr('ar', 'no_salon_title')), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
  });

  testWidgets('first screen is login; wrong code is refused; new customer registers and lands on home', (tester) async {
    final fake = Fake();
    await start(tester, fake);
    expect(find.text(tr('ar', 'first_time')), findsOneWidget);
    expect(Directionality.of(tester.element(find.byKey(const Key('phone')))), TextDirection.rtl);
    await tester.enterText(find.byKey(const Key('phone')), '55550001');
    await tester.tap(find.byKey(const Key('send')));
    await tester.pumpAndSettle();
    expect(find.textContaining('123456'), findsOneWidget); // test-environment code banner
    await tester.enterText(find.byKey(const Key('code')), '000000');
    await tester.tap(find.byKey(const Key('verify')));
    await tester.pumpAndSettle();
    expect(find.text(tr('ar', 'err_otp_invalid')), findsOneWidget);
    await tester.enterText(find.byKey(const Key('code')), '123456');
    await tester.tap(find.byKey(const Key('verify')));
    await tester.pumpAndSettle();
    expect(find.text(tr('ar', 'register_title')), findsOneWidget);
    await tester.enterText(find.byKey(const Key('name')), 'أم سارة');
    await tester.tap(find.text(tr('ar', 'add_child')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('child0')), 'سارة');
    await tester.tap(find.byKey(const Key('register')));
    await tester.pumpAndSettle();
    expect(find.text(tr('ar', 'hello', {'name': 'أم'})), findsOneWidget);
    // nearest branch first, marked as recommended
    expect(find.text(tr('ar', 'nearest')), findsOneWidget);
    expect(tester.getTopLeft(find.text('الجهراء')).dy, lessThan(tester.getTopLeft(find.text('حولي')).dy));
  });

  testWidgets('booking flow starts with services and suggests the nearest branch', (tester) async {
    final fake = Fake();
    SharedPreferences.setMockInitialValues({'token:${Uri.base.host}': 'T1'});
    final c = AppController(api: fake.api(), prefs: await SharedPreferences.getInstance(), locate: false);
    await tester.pumpWidget(QassaApp(controller: c));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('book_now')));
    await tester.pumpAndSettle();
    expect(find.text(tr('ar', 'step_service')), findsWidgets);
    await tester.tap(find.text('قص شعر'));
    await tester.pumpAndSettle();
    expect(find.text(tr('ar', 'step_branch')), findsWidgets);
    expect(find.text(tr('ar', 'other_branches')), findsOneWidget);
  });
}

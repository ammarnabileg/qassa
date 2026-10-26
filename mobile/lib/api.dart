import 'dart:convert';

import 'package:http/http.dart' as http;

import 'config.dart';

class ApiError implements Exception {
  ApiError(this.status, this.code, [this.details = const {}]);
  final int status;
  final String code;
  final Map<String, dynamic> details;
  @override
  String toString() => 'ApiError($status, $code)';
}

typedef Json = Map<String, dynamic>;

class Branch {
  Branch(this.j);
  final Json j;
  int get id => j['id'] as int;
  String name(String lang) => lang == 'en' && (j['name_en'] as String? ?? '').isNotEmpty ? j['name_en'] as String : j['name_ar'] as String;
  String get businessType => j['business_type'] as String;
  String get address => (j['address'] as String?) ?? '';
  String get phone => (j['phone'] as String?) ?? '';
  String get hours => '${j['opens_at']}–${j['closes_at']}';
  double? get distanceKm => (j['distance_km'] as num?)?.toDouble();
  bool get recommended => (j['recommended'] as bool?) ?? false;
}

class ServiceItem {
  ServiceItem(this.j);
  final Json j;
  int get id => j['id'] as int;
  int get category => j['category'] as int;
  String get businessType => j['business_type'] as String;
  String name(String lang) => lang == 'en' && (j['name_en'] as String? ?? '').isNotEmpty ? j['name_en'] as String : j['name_ar'] as String;
  int get minutes => j['duration_minutes'] as int;
  String get price => j['price'] as String;
}

class Catalog {
  Catalog(Json j)
      : salonName = (j['salon'] as Json)['name'] as String,
        businessType = (j['salon'] as Json)['business_type'] as String,
        branches = [for (final b in j['branches'] as List) Branch(b as Json)],
        categories = [for (final c in j['categories'] as List) c as Json],
        services = [for (final s in j['services'] as List) ServiceItem(s as Json)];
  final String salonName, businessType;
  final List<Branch> branches;
  final List<Json> categories;
  final List<ServiceItem> services;
}

class Me {
  Me(Json j)
      : fullName = j['full_name'] as String,
        phone = j['phone'] as String,
        beneficiaries = [for (final b in j['beneficiaries'] as List) b as Json];
  final String fullName, phone;
  final List<Json> beneficiaries;
}

/// Customer app API. On a company's own domain the salon is the host; elsewhere (store app, local testing)
/// it is sent as X-Salon. The login token is per salon (D-003, D-005).
class Api {
  Api({http.Client? client, String? baseUrl, this.salonSlug})
      : _client = client ?? http.Client(),
        _base = baseUrl ?? (Config.apiUrl.isEmpty ? Uri.base.origin : Config.apiUrl);
  final http.Client _client;
  final String _base;
  final String? salonSlug;
  String? token;

  Map<String, String> get _headers => {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        if (salonSlug != null) 'X-Salon': salonSlug!,
        if (token != null) 'Authorization': 'Customer $token',
      };

  Future<dynamic> _send(String method, String path, {Object? body, String? idempotencyKey}) async {
    final http.Response res;
    try {
      final uri = Uri.parse('$_base/api/v1/app$path');
      final h = {..._headers, if (idempotencyKey != null) 'Idempotency-Key': idempotencyKey};
      res = method == 'GET' ? await _client.get(uri, headers: h) : await _client.post(uri, headers: h, body: jsonEncode(body ?? {}));
    } catch (_) {
      throw ApiError(0, 'network');
    }
    final text = utf8.decode(res.bodyBytes);
    final data = text.isEmpty ? null : jsonDecode(text);
    if (res.statusCode >= 400) {
      final e = (data is Map ? data['error'] : null) as Map?;
      if (res.statusCode == 401 || res.statusCode == 403) throw ApiError(res.statusCode, 'auth');
      throw ApiError(res.statusCode, (e?['code'] as String?) ?? 'unknown', (e?['details'] as Map?)?.cast<String, dynamic>() ?? {});
    }
    return data;
  }

  Future<Catalog> catalog({double? lat, double? lng}) async =>
      Catalog(await _send('GET', '/catalog${lat != null ? '?lat=$lat&lng=$lng' : ''}') as Json);
  Future<Json> requestCode(String phone, String lang) async => await _send('POST', '/otp/request', body: {'phone': phone, 'lang': lang}) as Json;
  Future<Json> verifyCode(String phone, String code) async => await _send('POST', '/otp/verify', body: {'phone': phone, 'code': code}) as Json;
  Future<Json> register(Json body) async => await _send('POST', '/register', body: body) as Json;
  Future<Me> me() async => Me(await _send('GET', '/me') as Json);
  Future<Me> addChild(Json body) async => Me(await _send('POST', '/me/beneficiaries', body: body) as Json);
  Future<Json> slots(int branchId, int serviceId, String date, {int? staffId}) async =>
      await _send('GET', '/slots?branch_id=$branchId&service_id=$serviceId&date=$date${staffId != null ? '&staff_id=$staffId' : ''}') as Json;
  Future<Json> book(Json body, String key) async => await _send('POST', '/bookings', body: body, idempotencyKey: key) as Json;
  Future<List<Json>> bookings() async => [for (final b in await _send('GET', '/bookings') as List) b as Json];
  Future<Json> cancel(int id) async => await _send('POST', '/bookings/$id/cancel') as Json;
}

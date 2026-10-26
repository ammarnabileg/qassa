import 'dart:convert';

import 'package:http/http.dart' as http;

import 'config.dart';

class ApiError implements Exception {
  ApiError(this.status, this.code);
  final int status;
  final String code;
  @override
  String toString() => 'ApiError($status, $code)';
}

class Branch {
  Branch({required this.id, required this.nameAr, required this.nameEn, required this.businessType, required this.address, required this.phone});
  factory Branch.fromJson(Map<String, dynamic> j) => Branch(
      id: j['id'] as int,
      nameAr: j['name_ar'] as String,
      nameEn: (j['name_en'] as String?) ?? '',
      businessType: j['business_type'] as String,
      address: (j['address'] as String?) ?? '',
      phone: (j['phone'] as String?) ?? '');
  final int id;
  final String nameAr, nameEn, businessType, address, phone;
  String name(String lang) => lang == 'en' && nameEn.isNotEmpty ? nameEn : nameAr;
}

class Salon {
  Salon({required this.slug, required this.name, required this.businessType, required this.branches, this.locked = false});
  factory Salon.fromJson(Map<String, dynamic> j) => Salon(
      slug: j['slug'] as String,
      name: j['name'] as String,
      businessType: j['business_type'] as String,
      branches: [for (final b in j['branches'] as List) Branch.fromJson(b as Map<String, dynamic>)],
      locked: (j['locked'] as bool?) ?? false);
  final String slug, name, businessType;

  /// Served on the company's own domain: the app shows only this salon (no "change salon").
  final bool locked;
  final List<Branch> branches;
}

class Api {
  Api({http.Client? client, String? baseUrl}) : _client = client ?? http.Client(), _base = baseUrl ?? (Config.apiUrl.isEmpty ? Uri.base.origin : Config.apiUrl);
  final http.Client _client;
  final String _base;

  /// The salon that owns the current host (company subdomain or custom domain); 404 on the platform host.
  Future<Salon> salonForHost() => _get('/api/v1/public/salon');

  Future<Salon> salon(String slug) => _get('/api/v1/public/salons/${Uri.encodeComponent(slug)}');

  Future<Salon> _get(String path) async {
    final http.Response res;
    try {
      res = await _client.get(Uri.parse('$_base$path'), headers: {'Accept': 'application/json'});
    } catch (_) {
      throw ApiError(0, 'network');
    }
    final body = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>? ?? {};
    if (res.statusCode != 200) throw ApiError(res.statusCode, ((body['error'] as Map?)?['code'] as String?) ?? 'unknown');
    return Salon.fromJson(body);
  }
}

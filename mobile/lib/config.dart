/// Build-time configuration, injected by tool/build.sh via --dart-define. Nothing secret lives here.
class Config {
  static const apiUrl = String.fromEnvironment('API_URL', defaultValue: 'http://localhost:8000');
  static const version = String.fromEnvironment('QASSA_VERSION', defaultValue: 'unknown');
  /// Set for a salon's own store app (mobile/salons/SLUG.json): the app opens only that salon.
  static const salonSlug = String.fromEnvironment('SALON_SLUG');
  static const channel = String.fromEnvironment('QASSA_CHANNEL', defaultValue: 'debug');
}

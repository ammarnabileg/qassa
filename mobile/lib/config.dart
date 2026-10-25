/// Build-time configuration, injected by tool/build.sh via --dart-define. Nothing secret lives here.
class Config {
  static const apiUrl = String.fromEnvironment('API_URL', defaultValue: 'http://localhost:8000');
  static const version = String.fromEnvironment('QASSA_VERSION', defaultValue: 'unknown');
  static const channel = String.fromEnvironment('QASSA_CHANNEL', defaultValue: 'debug');
}

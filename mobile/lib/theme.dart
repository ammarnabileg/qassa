import 'package:flutter/material.dart';

/// Same palette as frontend/src/styles/tokens.css: one app, theme by business type.
const _brand = {'kids': Color(0xFF0CD273), 'men': Color(0xFFC9A24B), 'women': Color(0xFFEC6F9A)};

ThemeData themeFor(String? businessType, Brightness brightness) => ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(seedColor: _brand[businessType] ?? _brand['kids']!, brightness: brightness),
    );

#!/usr/bin/env python3
"""Prepare the build for one salon's own store app (D-014).

    python3 tool/salon_app.py <slug>      # run from mobile/, before `flutter build`

Reads salons/<slug>.json and writes, in the working tree only (CI; never commit the result):
  android/salon.properties   applicationId + launcher label
  launcher icons             Android mipmaps and the iOS AppIcon set, from salons/<slug>.png (1024x1024)
                             or, without one, the Qassa mark drawn in the salon's brand colour
  iOS                        bundle id (Runner) and display name
Prints the --dart-define flags for `flutter build` (SALON_SLUG locks the app to the salon).
"""
import json
import plistlib
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BRAND = {"kids": "#0CD273", "men": "#C9A24B", "women": "#EC6F9A"}
INK, SUN = "#081510", "#FFC83D"
ID = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


def mark(biz: str, size: int = 1024) -> Image.Image:
    """Same drawing as LogoMark (lib/theme.dart), on a 64-unit grid, rendered 4x and scaled down."""
    k = size * 4 / 64
    img = Image.new("RGBA", (size * 4, size * 4), BRAND.get(biz, BRAND["kids"]))
    d = ImageDraw.Draw(img)
    P = lambda pts: [(x * k, y * k) for x, y in pts]
    if biz == "men":
        d.ellipse(P([(20, 12), (32, 19)]), fill=INK)
        d.ellipse(P([(32, 12), (44, 19)]), fill=INK)
    elif biz == "women":
        d.polygon(P([(32, 15), (23, 9), (23, 21)]), fill="white")
        d.polygon(P([(32, 15), (41, 9), (41, 21)]), fill="white")
    else:
        d.polygon(P([(20, 15), (24, 10), (28, 15), (32, 10), (36, 15), (40, 10), (44, 15), (44, 19), (20, 19)]), fill=SUN)
    w = int(4 * k)
    for cx in (23, 41):
        d.ellipse(P([(cx - 6, 40), (cx + 6, 52)]), outline=INK, width=w)
    d.line(P([(27, 41), (41, 24)]), fill=INK, width=w)
    d.line(P([(37, 41), (23, 24)]), fill=INK, width=w)
    for a, b in (((41, 24), (41, 24)), ((23, 24), (23, 24))):  # round caps
        d.ellipse(P([(a[0] - 2, a[1] - 2), (b[0] + 2, b[1] + 2)]), fill=INK)
    return img.resize((size, size), Image.LANCZOS)


def main(slug: str) -> None:
    cfg = json.loads((ROOT / "salons" / f"{slug}.json").read_text(encoding="utf-8"))
    for k in ("slug", "app_name", "android_id", "ios_bundle_id", "business_type"):
        if not cfg.get(k):
            sys.exit(f"salons/{slug}.json: missing {k}")
    for k in ("android_id", "ios_bundle_id"):
        if not ID.match(cfg[k].lower()):
            sys.exit(f"salons/{slug}.json: {k} must look like com.salon.app")
    (ROOT / "android" / "salon.properties").write_text(
        f"appId={cfg['android_id']}\nappName={cfg['app_name']}\n", encoding="utf-8")

    src = ROOT / "salons" / f"{slug}.png"
    icon = Image.open(src).convert("RGBA").resize((1024, 1024), Image.LANCZOS) if src.exists() else mark(cfg["business_type"])
    icon = icon.convert("RGB")  # the stores reject transparent icons
    res = ROOT / "android" / "app" / "src" / "main" / "res"
    for folder, px in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
        icon.resize((px, px), Image.LANCZOS).save(res / f"mipmap-{folder}" / "ic_launcher.png")
    iconset = ROOT / "ios" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"
    for img in json.loads((iconset / "Contents.json").read_text())["images"]:
        if "filename" in img:
            px = round(float(img["size"].split("x")[0]) * int(img["scale"].rstrip("x")))
            icon.resize((px, px), Image.LANCZOS).save(iconset / img["filename"])

    pbx = ROOT / "ios" / "Runner.xcodeproj" / "project.pbxproj"
    text = pbx.read_text()
    text = re.sub(r"PRODUCT_BUNDLE_IDENTIFIER = app\.qassa\.qassaApp;", f"PRODUCT_BUNDLE_IDENTIFIER = {cfg['ios_bundle_id']};", text)
    text = text.replace("PRODUCT_BUNDLE_IDENTIFIER = app.qassa.qassaApp.RunnerTests;", f"PRODUCT_BUNDLE_IDENTIFIER = {cfg['ios_bundle_id']}.RunnerTests;")
    pbx.write_text(text)
    plist = ROOT / "ios" / "Runner" / "Info.plist"
    data = plistlib.loads(plist.read_bytes())
    data["CFBundleDisplayName"] = cfg["app_name"]
    data["CFBundleName"] = cfg["app_name"][:15]
    plist.write_bytes(plistlib.dumps(data))

    api = cfg.get("api_url", "")
    print(f"--dart-define=SALON_SLUG={slug}" + (f" --dart-define=API_URL={api}" if api else ""))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])

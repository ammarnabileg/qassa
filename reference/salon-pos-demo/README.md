# Qassa POS — Salon POS Demo (قصّة POS)

ديمو كامل لسيستم كاشير وحجوزات للصالونات (أطفال / رجالي / نسائي) — عربي وإنجليزي.
A complete demo of a POS & booking system for salons (kids / men / women) — Arabic & English.

> **ده ديمو للعرض، مش نسخة إنتاج.** كل البيانات بتتخزن في متصفح الجهاز (localStorage)، ومفيش سيرفر.
> **This is a demo, not production software.** All data lives in the browser (localStorage); there is no backend.

---

## التشغيل / Run

| الطريقة / Method | الأمر / Command |
|---|---|
| أسهل طريقة: افتح الملف مباشرة / Easiest: open directly | دبل كليك على `index.html` / double-click `index.html` |
| سيرفر محلي (أفضل) / Local server (recommended) | `python3 -m http.server 8080` ثم/then `http://localhost:8080` |
| أو / or | `npx serve .` |
| رفعه أونلاين / Host online | ارفع الفولدر كما هو على Netlify / Vercel / GitHub Pages / أي استضافة static |

مفيش build ولا `npm install`. / No build step and no dependencies.

## الحسابات التجريبية / Demo accounts

كلمة المرور لكل الحسابات / Password for all: **`123456`**

| الدور / Role | Email | النوع / Type |
|---|---|---|
| مالك المنصة / Platform owner | `owner@qassa.io` | — |
| صاحب شركة / Company owner | `owner@mykids.com` | 🧒 أطفال / Kids |
| صاحب شركة / Company owner | `owner@gentle.com` | 💈 رجالي / Men |
| صاحبة شركة / Company owner | `owner@lamsa.com` | 💅 نسائي / Women |
| مدير فرع / Branch manager | `hawally@mykids.com` (`salmiya@…`, `jahra@…`) | 🧒 |
| كاشير / Cashier | `cashier@mykids.com` | 🧒 |

نفس الأدوار موجودة للرجالي والنسائي بدومين `gentle.com` و`lamsa.com`.
The same roles exist for men/women under `gentle.com` and `lamsa.com`.

**روابط مباشرة / Direct links:**
- `index.html#/pricing` — صفحة الأسعار العامة / public pricing page
- `index.html#/app/kids` · `#/app/men` · `#/app/women` — تطبيق العملاء / customer booking app (رقم/phone `55123456`، أي كود من 4 أرقام / any 4-digit code)

## الخدمة المنزلية والسبا / Home service & spa

- **الحجز المنزلي (كل الأنواع) / Home booking (all types):** العميل بيختار "في البيت" في تطبيق الحجز ويكتب العنوان. الحجز بيظهر في طابور الفرع بعلامة 🏠 والعنوان ورابط الخريطة، ورسوم الزيارة بتتضاف للفاتورة تلقائياً.
  Customers pick "At home" in the app and enter their address; the booking shows in the branch queue with 🏠, the address and a map link, and the visit fee is added to the invoice.
- **الإعدادات ← الخدمة المنزلية / Settings → Home service:** تشغيل/إيقاف، رسوم الزيارة، أقل فاتورة، أقل وقت قبل المعاد، المناطق، والخدمات الممنوعة في البيت.
  On/off, visit fee, minimum invoice, minimum notice, service areas, and services not available at home.
- **المساج والسبا (نسائي) / Massage & spa (women):** مساج استرخاء، أحجار ساخنة، رجلين، رأس ورقبة، حمام مغربي، صنفرة، تنظيف بشرة، ماسك ذهب، ساونا + عرض "يوم سبا". الحمام المغربي والساونا مش متاحين في البيت.
  Relaxing, hot stone, foot, head & neck massage, Moroccan bath, scrub, facial, gold mask, sauna + a "Spa day" bundle. Moroccan bath and sauna are salon-only.

## وضع التابلت / آيباد — Tablet / iPad cashier mode

- زرار **"📱 وضع التابلت"** في شاشة الكاشير، وبيشتغل تلقائياً للكاشير على أي جهاز لمس. / Button in the POS, and auto-enabled for cashiers on touch devices.
- **أفقي / Landscape:** الخدمات يمين والفاتورة شمال، وكل جزء بيسكرول لوحده. / Services and invoice side by side, each scrolls independently.
- **رأسي / Portrait:** الفاتورة بتطلع من تحت كـ bottom sheet بشريط إجمالي ثابت. / The invoice opens as a bottom sheet from a fixed total bar.
- أزرار كبيرة للمس، اختيار الحلاق بالصور، طابور اليوم (اضغط ← فاتورة)، لوحة أرقام للكاش مع "بالظبط / 5 / 10 / 20". / Large touch targets, barber chips, today's queue (tap → invoice), cash keypad with Exact / 5 / 10 / 20.
- نفس منطق الكاشير العادي بالظبط (كوبونات، نقاط، حجوزات مدفوعة، زيارات منزلية). / Same logic as the desktop POS.
- الملفات / Files: `assets/css/tablet.css`, `js/apps/tablet-pos.js`.
- لتثبيته كتطبيق على الآيباد: افتحه في Safari ← مشاركة ← "إضافة إلى الشاشة الرئيسية". / To install on iPad: Safari → Share → Add to Home Screen.

## الصلاحيات / Roles

```
مالك المنصة (أنت)         Platform owner (you)
 └─ صاحب الشركة            Company owner      — كل الفروع، الأسعار، العروض، النقاط، الموظفين، الإعدادات
     └─ مدير الفرع          Branch manager     — فرعه بس: كاشير، حجوزات، مخزون، مصروفات، خزينة، تقارير
         └─ الكاشير          Cashier            — كاشير، حجوزات، فواتير، عملاء، أرصدة النقاط
```

## اللغة / Language

زرار 🌐 في القائمة وصفحة الدخول وصفحة الأسعار والتطبيق. الاختيار بيتحفظ.
The 🌐 button in the sidebar, login, pricing page and customer app. The choice is remembered.

## هيكل الملفات / Project structure

```
salon-pos-demo/
├── index.html                    الصفحة الوحيدة + أيقونات SVG / single page + inline SVG icon sprite
├── assets/
│   ├── css/
│   │   ├── base.css              الألوان والمكونات (Tahseen design system) / tokens & components
│   │   ├── site.css              صفحة الأسعار / pricing site
│   │   ├── customer-app.css      تطبيق العملاء / customer app
│   │   ├── themes.css            ثيم كل نوع نشاط / per business-type themes
│   │   └── responsive.css        الموبايل والإنجليزي والطباعة / mobile, LTR & print
│   ├── fonts/                    Alexandria (عربي + لاتيني)
│   └── icons/sprite.svg          نسخة من الأيقونات / icon sprite (copy)
└── js/
    ├── core/
    │   ├── config.js             القوائم والأدوار وطرق الدفع / nav, roles, payment methods
    │   ├── i18n.js               محرك اللغة / language engine
    │   ├── business-types.js     أطفال/رجالي/نسائي: ثيم + مصطلحات / theme + wording per type
    │   ├── helpers.js            دوال مساعدة / helpers
    │   └── auth-nav.js           الدخول والصلاحيات والتنقل / login, permissions, routing
    ├── i18n/en.js                القاموس الإنجليزي / English dictionary ("عربي|English" per line)
    ├── data/
    │   ├── seeds.js              بيانات كل نوع نشاط والتخزين / seed data per type & storage
    │   └── demo.js               فواتير تجريبية أول تشغيل / first-run demo transactions
    ├── modules/                  شاشات السيستم / back-office screens
    │   ├── company.js            لوحة صاحب الشركة والفروع / company dashboard & branches
    │   ├── home.js  pos.js  bookings.js  invoices.js  customers.js
    │   ├── services-stock.js  staff.js  expenses.js  cash.js  reports.js
    │   ├── offers.js  loyalty.js  settings.js
    ├── apps/
    │   ├── customer-app.js       تطبيق الحجز والدفع للعملاء / booking & payment app
    │   └── pricing-site.js       صفحة الأسعار والتسجيل / pricing & signup site
    ├── platform/
    │   ├── platform.js           لوحة المنصة: الشركات والباقات والفواتير والدعم / platform panel
    │   └── platform-config.js    إعدادات المنصة (بتغذي صفحة الأسعار) / settings feeding pricing page
    ├── integrations/whatsapp.js  رسائل واتساب / WhatsApp messages (wa.me)
    ├── ui/service-art.js         رسومات الخدمات / service illustrations
    └── main.js                   بدء التشغيل / app start
```

ترتيب تحميل ملفات JS في `index.html` مهم — متغيرهوش.
The `<script>` order in `index.html` matters — keep it.

## تعديلات شائعة / Common edits

| عايز / Want to | الملف / File |
|---|---|
| تغيير الخدمات والأسعار الافتراضية / default services & prices | `js/data/seeds.js` (أو من الشاشة / or from the Services screen) |
| ترجمة جملة جديدة / translate a new phrase | سطر جديد في / add a line to `js/i18n/en.js` |
| ألوان نوع نشاط / business-type colors | `assets/css/themes.css` |
| مصطلحات رجالي/نسائي / men/women wording | `js/core/business-types.js` (`TERM_MAPS`, `EN_TERM_MAPS`) |
| الباقات وأسعار الاشتراك / subscription plans | من لوحة المنصة / Platform → Plans (أو / or `js/platform/platform.js`) |

**تصفير الديمو / Reset the demo:** الإعدادات ← البيانات ← مسح كل الحركات، أو امسح بيانات الموقع من المتصفح.
Settings → Data → Delete all transactions, or clear the site data in the browser.

## حدود الديمو / Demo limitations

| الموضوع / Topic | في الديمو / In the demo | المطلوب للإنتاج / Needed for production |
|---|---|---|
| البيانات / Data | localStorage لكل جهاز / per device | Backend + database (`tenant_id`, `branch_id` على كل جدول / on every table) |
| الأمان / Security | الصلاحيات في الواجهة بس / UI-only | Server-side auth & authorization |
| الدفع / Payments | شاشة تجريبية / simulated | MyFatoorah / Tap / UPayments (KNET) |
| واتساب / WhatsApp | `wa.me` — الموظف بيضغط إرسال / staff taps Send | WhatsApp Business API للإرسال التلقائي / for automation |
| SMS / OTP | أي كود / any code | SMS provider |
| الترجمة / Translation | قاموس بيستبدل النص على الشاشة / runtime phrase dictionary | i18n keys (`t('pos.title')`) |
| تطبيق العملاء / Customer app | معاينة جوه الصفحة / in-page preview | PWA أو / or Flutter / React Native |
| نسائي / Women | أسعار متغيرة بس / variable prices only | حجز متعدد الخدمات، باقات جلسات، خصم مواد / multi-service booking, session packages, material usage |

## الهوية / Design

مبني على Tahseen design system (الألوان، الخط Alexandria، المكونات).
Built on the Tahseen design system (tokens, Alexandria font, components).

# SYSTEM_HANDOVER — قصّة POS (Qassa POS)

> **تاريخ التسليم:** 2026-11-01
> **آخر commit للكود:** `8dbf125` على `main`. ملف التسليم ده بيتضاف في commit بعده.
> **مصادر التسليم:**
> - فحص مباشر للمستودع.
> - تشغيل الاختبارات في جلسة العمل.
> - فحص السيرفر التجريبي من المتصفح.
> - المحادثة مع صاحب المشروع.
>
> **رموز الحالة** المستخدمة في الجداول:
> - **مكتملة**: كود + اختبارات تعدّي + اتجربت فعلياً.
> - **مكتملة جزئياً**: شغالة، لكن ناقصها جزء محدد مكتوب جنبها.
> - **واجهة فقط**: الشاشة موجودة من غير منطق حقيقي وراها.
> - **لم تُنفذ**: مش موجودة في الكود.
> - **غير مؤكدة**: الكود موجود، لكن ما اتأكدش من تشغيلها في بيئة حقيقية.
>
> هذا الملف لا يحتوي على أي كلمة مرور أو مفتاح أو توكن. كل الأسرار موجودة في Coolify أو GitHub Secrets.

---

## 1. نظرة عامة على النظام

**الاسم:** قصّة POS (Qassa POS). المستودع: `ammarnabileg/qassa`.

**الهدف:** نظام SaaS متعدد الشركات (multi-tenant) لصالونات الكويت: صالونات الأطفال والرجالي والحريمي. الشركة الواحدة ممكن يكون عندها أكثر من فرع. يجمع النظام في مكان واحد:
- الكاشير.
- الحجوزات.
- العملاء وأطفالهم.
- الموظفين والعمولات.
- المخزون.
- الولاء والعروض.
- المحاسبة الكاملة: قيد مزدوج، وقوائم مالية، وملف وزارة التجارة (XBRL).
- رسائل واتساب من رقم الصالون نفسه.
- تطبيق للعملاء (PWA وAndroid وiOS).

**المشكلة التي يحلها:** صاحب الصالون في العادة:
- مش عارف كسب كام في اليوم.
- مش قادر يتحكم في الكاش، والموظف ممكن يسرق.
- بيخسر فلوس من العملاء اللي بيحجزوا وما بيجوش.
- بيدير الحجز على الورق أو على الواتساب.

النظام يقفل الدرج بالعدّ ويطلّع العجز، ويبعت تذكيرات، ويعمل القيود المحاسبية تلقائياً.

**المستخدمون والأدوار** (الأدوار الجاهزة في `backend/apps/tenancy/permissions_catalog.py`):

| الدور | المفتاح | ملاحظة |
|---|---|---|
| فريق المنصة | `User.is_platform_staff` | يدير الشركات والباقات وفواتير الاشتراك والدعم |
| مالك الشركة | `owner` | له كل الصلاحيات دائماً، ولا يمكن تقييده |
| مدير العمليات | `operations_manager` | كل الصلاحيات ما عدا المحاسبة الحساسة |
| مدير الفرع | `branch_manager` | |
| كاشير واستقبال | `cashier` | |
| مقدم خدمة | `service_provider` | |
| مسؤول المخزون | `inventory_officer` | |
| محاسب | `accountant` | |
| المدير المالي | `finance_manager` | |
| مراجع خارجي | `auditor` | |
| أدوار مخصصة | `custom-xxxxxxxx` | يعملها المالك أو من له صلاحية `users.manage` |
| عميل الصالون | — | يستخدم تطبيق العملاء، ويدخل بكود واتساب (OTP) |

**دورة العمل من البداية للنهاية:**
1. **إنشاء الشركة:** فريق المنصة ينشئها من لوحة المنصة على `kuw1.com`.
   - يختار العنوان الفرعي، والباقة، والفروع، وبيانات المالك.
   - إذا لم يكن هناك بريد إلكتروني ولا واتساب، يظهر لينك تعيين الباسورد في الشاشة لينسخه الفريق ويرسله.
2. **دخول المالك:** يدخل على `<slug>.kuw1.com/dashboard`.
   - يضبط: الفروع ومواعيدها، والخدمات والأسعار، والموظفين ومهاراتهم ومواعيدهم.
   - يضيف المستخدمين ويحدد صلاحياتهم، ويربط رقم واتساب الصالون بـ QR.
3. **العميل:** يفتح `<slug>.kuw1.com`، يدخل بكود واتساب، ويحجز.
4. **الاستقبال والكاشير:**
   - يفتح الدرج، ويستقبل الحجز أو الطابور.
   - يعمل الفاتورة: خدمات ومنتجات وباقات، وخصم أو كوبون أو نقاط، ودفع نقدي أو كي-نت أو تحويل أو آجل.
   - يطبع الإيصال أو يرسله على واتساب.
5. **القيود والعمولات:** كل عملية تولّد قيوداً محاسبية تلقائية، وتسجّل عمولة الموظف.
6. **نهاية اليوم:** إقفال الدرج بالعدّ حسب فئات العملة، ومدير يوافق على أي عجز أو زيادة.
7. **المحاسبة:**
   - المصروفات، والأصول والإهلاك، وتسويات الكي-نت.
   - قائمة الدخل والميزانية، وإقفال الفترات، وتصدير ملف وزارة التجارة.
8. **الاشتراك:** المنصة تصدر فاتورة اشتراك شهرية، والتحصيل يدوي ويُسجَّل بمرجع.

---

## 2. التقنيات والبنية

| الجزء | التقنية | الإصدار (من الملفات) |
|---|---|---|
| الخلفية | Python 3.13، Django 5.2.18، DRF 3.18.3، drf-spectacular 0.30.0، django-otp 1.7.5، Celery 5.6.3، gunicorn، openpyxl 3.1.5 | `backend/requirements.txt` |
| قاعدة البيانات | PostgreSQL 16 | `docker-compose.yml`، CI |
| الطوابير والكاش | Redis 7 (Celery broker + cache + rate limits) | |
| الواجهة الإدارية | React 19، TypeScript ~6.0، Vite 8، React Router 7، TanStack Query 5، i18next | `frontend/package.json` |
| تطبيق العملاء | Flutter 3.47.8 (Android وiOS وWeb/PWA) | `mobile/pubspec.yaml`، workflows |
| الخادم | nginx (web) ← gunicorn (backend)، خلف Traefik الخاص بـ Coolify | `deploy/` |
| الاستضافة | Coolify على سيرفر ARM، والنطاق `kuw1.com` (DNS على Cloudflare) | المحادثة |
| واتساب | Evolution API (غير رسمي)، على السيرفر `webs.onz.one` | Coolify env |

```mermaid
flowchart LR
  subgraph Browser
    A[kuw1.com<br/>الموقع العام + لوحة المنصة]:::r
    B["<slug>.kuw1.com/dashboard<br/>لوحة الصالون React"]:::r
    C["<slug>.kuw1.com<br/>PWA العملاء Flutter"]:::f
  end
  M[تطبيق Android/iOS<br/>Flutter] --> T
  A & B & C --> T[Traefik / Coolify<br/>TLS]
  T --> N[nginx web<br/>React تحت /_q/ و PWA]
  N -->|/api/| G[gunicorn Django]
  G --> P[(PostgreSQL 16)]
  G --> R[(Redis)]
  W[Celery worker + beat] --> P
  W --> R
  W -->|outbox| E[Evolution API واتساب]
  W -->|اختياري D-016| CF[Coolify API]
  classDef r fill:#e8f8ef; classDef f fill:#eef;
```

**طريقة ارتباط المكونات:**
- **تحديد الشركة من النطاق:** `HostMiddleware` (`backend/apps/platform/middleware.py`) يحدد الشركة من اسم النطاق عبر جدول `TenantDomain`، ويرفض أي نطاق غير مسجل بـ 400.
- **اختيار الشركة في الطلب:** الواجهة الإدارية ترسل header اسمه `X-Tenant`. على نطاق صالون، الـ API يرفض أي شركة غير صاحبة النطاق (D-015).
- **تطبيق العملاء:** يستخدم token خاص (`Authorization: Customer <token>`) على مسارات `/api/v1/app/*`.
- **المهام الخلفية:** تمر عبر Outbox (`apps/core/services/infra.py`)، وCelery يعالجها كل 5 ثوانٍ.
- **المهام المجدولة** (`backend/qassa/celery.py`، بتوقيت UTC):
  - `deliver-outbox` كل 5 ثوانٍ.
  - `booking-reminders` كل 15 دقيقة.
  - `daily-billing` الساعة 01:10.
  - `daily-loyalty` الساعة 00:20.
  - `winback` الساعة 07:40.
  - `rebook` الساعة 07:10.

**أهم المجلدات:**

| المسار | الوظيفة |
|---|---|
| `backend/qassa/` | الإعدادات `settings.py`، والمسارات `urls.py`، و`celery.py` |
| `backend/apps/tenancy` | الشركات والكيانات القانونية والفروع والأدوار والعضويات والصلاحيات، و`api/users.py` للمستخدمين والأدوار |
| `backend/apps/identity` | المستخدمون والدخول والتحقق بخطوتين (TOTP أو واتساب) والأجهزة الموثوقة والدعوات |
| `backend/apps/platform` | الباقات والاشتراكات والنطاقات وفواتير المنصة والدعم والـ leads وإنشاء الشركات (`services/onboarding.py`) والمزامنة مع Coolify (`services/coolify.py`) |
| `backend/apps/catalog` | الخدمات والأقسام والأسعار المؤرخة |
| `backend/apps/staff` | الموظفون والمهارات والمواعيد والإجازات والعمولات |
| `backend/apps/customers` | العملاء والمستفيدون (الأطفال) وOTP تطبيق العملاء والاستيراد |
| `backend/apps/booking` | الحجوزات |
| `backend/apps/pos` | الدرج والفواتير والمرتجعات والمدفوعات والكاشير دون إنترنت والتقارير |
| `backend/apps/inventory` | المنتجات والمخزون والموردون والمشتريات |
| `backend/apps/loyalty` | الباقات المسبقة والكوبونات والنقاط والمستويات والهدايا |
| `backend/apps/accounting` | دليل الحسابات والقيود والفترات والمصروفات والأصول والتسويات والقوائم وXBRL |
| `backend/apps/notifications` | قناة واتساب والرسائل التلقائية والتقييمات |
| `backend/apps/audit` | سجل التدقيق |
| `backend/apps/core` | Idempotency وOutbox والأخطاء والتواريخ والـ throttling وقراءة Excel وCSV |
| `backend/tests/` | اختبارات pytest (30 ملف) |
| `frontend/src/pages/` | شاشات React |
| `frontend/src/i18n/{ar,en}.json` | كل نصوص الواجهة (اختبار يفشل لو الملفين اختلفوا) |
| `frontend/src/base.ts` | المسار الأساسي: `/dashboard` على نطاق الصالون، و`/_q/` للملفات |
| `frontend/public/sw.js` | service worker للعمل دون إنترنت |
| `mobile/` | تطبيق Flutter، وفيه `mobile/salons/*.json` و`mobile/tool/salon_app.py` لتطبيق خاص لكل صالون |
| `deploy/` | Dockerfiles، و`nginx.conf.template`، والـ PWA المبنية مسبقاً `deploy/pwa` |
| `docker-compose.yml` | تشغيل محلي |
| `docker-compose.prod.yml` | تشغيل الإنتاج والتجربة عبر Coolify |
| `docs/` | `ARCHITECTURE.md`، و`DECISIONS.md` (من D-001 لـ D-016)، و`openapi.yaml`، وتقارير المراحل، و`STATUS.md` (قديم، راجع §7) |
| `reference/salon-pos-demo/` | النسخة التجريبية الثابتة اللي التصميم لازم يطابقها. **ليست كود إنتاج** |
| `scripts/version.py` | حساب رقم الإصدار |
| `.github/workflows/` | `ci.yml`، و`release.yml`، و`build-mobile.yml`، و`build-pwa.yml`، و`build-salon-apps.yml` |

---

## 3. الوظائف الموجودة

### قواعد التصنيف المستخدمة هنا

**الحالة:**

| الحالة | معناها |
|---|---|
| **مكتملة** | اختبارات آلية تعدّي **و** تجربة فعلية للوظيفة نفسها (مش بس فتح الشاشة) |
| **مكتملة جزئياً** | شغالة، لكن فيه جزء محدد ناقص أو ما اتجربش، ومكتوب جنبها |
| **غير مؤكدة** | الكود والاختبارات الآلية موجودين، لكن ما اتجربتش في بيئة حقيقية، أو بتعتمد على خدمة خارجية ما اشتغلتش |
| **واجهة فقط** | الشاشة موجودة من غير منطق حقيقي وراها |
| **لم تُنفذ** | مش موجودة في الكود |

**أعمدة الجداول:**
- **اختبار آلي:** اختبارات pytest للـ backend. آخر تشغيل كامل كان 2026-11-01 على `8dbf125`، والنتيجة 176 passed. «لا يوجد» معناها مفيش اختبار آلي مخصص للوظيفة.
- **تجربة محلية:** متصفح آلي (Playwright) على سيرفر تطوير في بيئة العمل.
- **تجربة على السيرفر:** متصفح آلي على `qassa.kuw1.com` أو `kuw1.com` أو `<slug>.kuw1.com`. مكتوب جنبها الـ commit اللي كان منشور وقتها لو معروف.
  - «قبل `108ba4e`» معناها اتجربت في جلسات قديمة، والـ commit الدقيق **غير معروف**.
- **تنبيه:** السيرفر شغال دلوقتي على `9676fc5`. الـ commit-ين `f8583c3` و`8dbf125` **مش منشورين**، فأي وظيفة منهم ما اتجربتش على السيرفر.

### المنصة والهوية والصلاحيات

| الوظيفة | المفروض تعمل إيه | الحالة | الملفات | اختبار آلي | تجربة محلية | تجربة على السيرفر | لم يُختبر / نواقص |
|---|---|---|---|---|---|---|---|
| إنشاء شركة | الشركة والفروع ودليل الحسابات والأدوار والمالك والاشتراك | مكتملة | `platform/services/onboarding.py`، `pages/Platform.tsx` | نعم (`test_infra_audit_auth.py`، `test_domains.py`) | — | صاحب المشروع أنشأ صالون «MyKids» فعلاً، وظهر على `mykids.kuw1.com` (`76eb666`) | — |
| اختيار العنوان الفرعي وقت الإنشاء | فحص المتاح والمحجوز والمستخدم | مكتملة | `onboarding.check_subdomain`، `platform/subdomain-check` | نعم | — | API الفحص اتجرب لـ 3 أسماء (`76eb666`) | الفورم نفسه ما اتجربش بإنشاء شركة من المتصفح |
| اسم فرعي إضافي لصالون | زي `mykids.kuw1.com` جنب `my-kids.kuw1.com` | غير مؤكدة | `platform/api/views.py` (`TenantDomainsView`) | نعم | — | لا | ما اتجربش من الشاشة |
| دومين خاص للشركة | للباقات المسموح لها، ويتفعّل بعد الـ DNS | غير مؤكدة | نفس الملف | نعم | — | لا | ما اتجربش بدومين حقيقي |
| مزامنة النطاقات مع Coolify (D-016) | إضافة النطاق على خدمة `web` وعمل Deploy | غير مؤكدة | `platform/services/coolify.py` | نعم، بـ API وهمية | — | السيرفر بيقول إنها مفعلة (`auto_coolify: true`) | ما اتنشأتش شركة بعد التفعيل، فمش معروف إذا كان التوكن الجديد شغال |
| لينك باسورد المالك | يظهر عند الإنشاء، وفيه زرار لإعادة الإصدار | مكتملة جزئياً | `owner_link`، `OwnerInviteView` | نعم (إصدار اللينك وتعيين الباسورد بيه) | — | الزرار ظاهر في شركة MyKids (`e342595`) | ما اتضغطش على السيرفر عن قصد، لأن اللينك سري. ما اتأكدش إن المالك دخل فعلاً |
| الدخول والتحقق بخطوتين | باسورد، ثم TOTP أو كود واتساب، وتذكّر الجهاز | مكتملة جزئياً | `identity/` | نعم | نعم | الدخول بالباسورد لحسابات `e2e` (اللي مش عليها تحقق بخطوتين) على كل commit من المذكورين هنا | التحقق بخطوتين عبر واتساب ما اتجربش على السيرفر، لأن حالة رقم المنصة غير معروفة |
| نسيت الباسورد | بريد إلكتروني أو واتساب | غير مؤكدة | `identity/services/accounts.py` | نعم (بريد وهمي) | — | لا | SMTP مش متظبط في الإنتاج |
| دعوة مستخدم (لينك أو باسورد يحدده المدير، وأولوية الإرسال) | بريد، ثم واتساب المنصة، ثم واتساب الصالون، ثم زرار wa.me | مكتملة جزئياً | `tenancy/api/users.py`، `pages/Users.tsx` | نعم (`test_accounts_and_fallbacks.py`) | لا | لا (منشورة في `9676fc5`، لكن ما اتجربتش من المتصفح) | الواجهة ما اتجربتش |
| الأدوار والصلاحيات الدقيقة | تعديل الأدوار، وأدوار مخصصة، واستثناءات لكل شخص، وحماية ضد التصعيد | مكتملة جزئياً | `tenancy/models.py`، `api/users.py`، `components/PermissionPicker.tsx` | نعم (`test_permissions_control.py`) | شاشة الأدوار وفتح تعديل دور (`8dbf125`) | **لا، مش منشورة** | ما اتحفظش أي تعديل من المتصفح. استثناءات الشخص ما اتجربتش من الواجهة |
| عزل الشركات | كل استعلام مقيَّد بالشركة | مكتملة | `tenancy/scoping.py` | نعم (`test_tenancy_isolation.py`) | — | — | — |
| قفل نطاق الصالون | `/dashboard` على نطاق الصالون بيعرض الشركة دي بس | مكتملة | `tenancy/api/base.py`، `frontend/src/base.ts`، `deploy/nginx.conf.template` | نعم | — | دخول وكاشير وعملاء على `my-kids.kuw1.com/dashboard` (`3225df9`) | ما اتجربش من المتصفح إن مستخدم عضو في شركتين يشوف واحدة بس (ده متغطي في الاختبار الآلي) |
| حدود الطلبات (rate limit) | الدخول والـ OTP والـ leads | مكتملة جزئياً | `core/throttling.py` | نعم، بـ Redis حقيقي | — | لا | الـ IP الخارج من بيئة العمل بيتغير، فما ينفعش يتجرب على السيرفر من هنا |
| سجل التدقيق | تسجيل العمليات الحساسة | مكتملة جزئياً | `audit/` | نعم | — | غير معروف | شاشة السجل ما اتراجعتش |
| فواتير الاشتراك | إصدار شهري ومتأخرات وتسجيل الدفع | مكتملة جزئياً | `platform/services/billing.py` | نعم، ومعاه إصلاح يوم التجديد (`a8cdc15`) | — | الشاشة قبل `108ba4e`، وزرار التذكير على الواتساب (`bef797d`) | ما اتصدرتش فاتورة حقيقية بعد الإصلاح |
| الدعم والدخول كدعم فني | تذاكر الدعم، ودخول للقراءة فقط | مكتملة | `platform/api/console.py` | نعم | — | قبل `108ba4e` | — |
| الموقع العام وحاسبة التوفير | الأسعار وطلب التواصل والحاسبة | مكتملة | `pages/Landing.tsx`، `components/SavingsCalc.tsx` | لا يوجد | — | الحاسبة على `qassa.kuw1.com` (`53ba55f`) وعلى `kuw1.com` (`3225df9`) | إرسال طلب تواصل حقيقي ما اتجربش في الجلسة دي |
| بوابات الدفع في إعدادات المنصة | عرض بس: «غير متصلة» | واجهة فقط (مقصود) | `PlatformConsole.tsx` | لا | — | لا | لا يوجد مزود دفع |

### التشغيل اليومي

| الوظيفة | الحالة | الملفات | اختبار آلي | تجربة محلية | تجربة على السيرفر | لم يُختبر / نواقص |
|---|---|---|---|---|---|---|
| الكاشير (السلة والخصومات والكوبون والنقاط والباقات والدفع المتعدد والآجل والبقشيش) | مكتملة | `pos/services/sales.py`، `pages/POS.tsx` | نعم (`test_phase3_operations.py`، `test_phase4.py`) | — | فتح الكاشير على `my-kids.kuw1.com/dashboard/pos` (`3225df9`). البيع الكامل اتجرب قبل `108ba4e` | البيع ما اتعادش على `kuw1.com` بعد نقل النطاقات |
| اقتراح إضافة في الكاشير | غير مؤكدة | `pages/POS.tsx`، `catalog` (`upsell`) | نعم (حقل الخدمة) | لا | خانات الفورم ظاهرة (`53ba55f`) | الزرار «✨ ضيف …» ما ظهرش ولا اتضغط على السيرفر ولا محلياً |
| الدرج والإقفال بالعدّ والموافقة على العجز | مكتملة | `pos/`، `pages/Cash.tsx` | نعم | — | قبل `108ba4e` | — |
| المرتجعات (مع عكس العمولة والنقاط) | مكتملة جزئياً | `pos/services/sales.py` | نعم | — | غير معروف | — |
| الكاشير دون إنترنت (D-013) | مكتملة جزئياً | `pos/services/offline.py`، `pages/OfflinePOS.tsx`، `public/sw.js` | نعم (فيه مزامنة) | — | قبل `108ba4e` (قبل نقل الـ service worker) | **بعد نقل الـ service worker إلى `/_q/sw.js` (`8529e91`) ما اتجربش قطع الشبكة**. اللي اتأكد بس إن الـ scope اتسجل صح |
| إرسال الإيصال واتساب من رقم الصالون | غير مؤكدة | `notifications/api/views.py`، `pages/Invoices.tsx` | نعم (بوابة وهمية) | لا | **لا، مش منشورة** (`f8583c3`) | مفيش رقم صالون متصل |
| الحجوزات والطابور | مكتملة | `booking/`، `pages/Bookings.tsx` | نعم | — | قبل `108ba4e` | — |
| العملاء والأطفال | مكتملة | `customers/` | نعم | — | قائمة العملاء على `/dashboard/customers` (`3225df9`) | — |
| استيراد Excel وCSV | مكتملة جزئياً | `core/services/tabular.py`، `customers/services/importer.py`، `catalog/services/importer.py` | نعم (CSV وxlsx، والمعاينة والحفظ) | — | معاينة ملف CSV (`53ba55f`) | الحفظ ما اتعملش على السيرفر عن قصد. استيراد الخدمات من المتصفح ما اتجربش |
| الخدمات والأسعار المؤرخة | مكتملة | `catalog/` | نعم | — | فتح فورم الخدمة (`53ba55f`)، والسعر قبل `108ba4e` | — |
| الموظفين والعمولات والمواعيد | مكتملة | `staff/` | نعم | — | أعمدة الموظفين قبل `108ba4e` | — |
| المخزون والمشتريات | مكتملة | `inventory/` | نعم | — | قبل `108ba4e` | — |
| الباقات والكوبونات | مكتملة | `loyalty/` | نعم | — | قبل `108ba4e` | — |
| النقاط والمستويات والهدايا | مكتملة جزئياً | `loyalty/services/points.py`، `loyalty/tasks.py` | نعم (المستويات وأول زيارة وعيد الميلاد والانتهاء) | — | حفظ المستويات وعرضها (`9713a55`) | المهمة اليومية (عيد الميلاد والانتهاء) ما اتشافتش بتشتغل على السيرفر |
| التقييم بعد الزيارة | غير مؤكدة | `notifications/api/feedback.py`، `pages/Rate.tsx`، `pages/Feedback.tsx` | نعم (اللينك والتقييم مرة واحدة ولينك جوجل) | — | صفحة التقييم بلينك غلط، وشاشة التقييمات (`5d2cbe2`) | الإرسال الحقيقي محتاج رقم صالون متصل |
| «وحشتنا» و«وقت الزيارة الجاية» | غير مؤكدة | `notifications/auto.py` | نعم (بوابة وهمية) | — | الإعدادات ظاهرة (`5d2cbe2`) | محتاجة رقم متصل وعملاء موافقين على الرسائل التسويقية |
| الرسائل التلقائية (تأكيد وتذكير وإيصال) | غير مؤكدة | `notifications/auto.py` | نعم (بوابة وهمية) | — | — | أول محاولة إرسال حقيقية (كود دخول) فشلت لأن رقم الصالون مش متصل |
| ربط رقم واتساب الصالون بـ QR | غير مؤكدة | `notifications/whatsapp.py`، `pages/WhatsApp.tsx` | نعم (بوابة وهمية) | — | الشاشة بتجيب الحالة من Evolution: «مش مربوط» (`9676fc5`) | ما اتربطش أي رقم فعلاً |

### المحاسبة والتقارير

| الوظيفة | الحالة | الملفات | اختبار آلي | تجربة على السيرفر | لم يُختبر / نواقص |
|---|---|---|---|---|---|
| القيود التلقائية من كل عملية | مكتملة (السياسة مؤقتة) | `accounting/services/posting.py`، `pos/services/ledger.py` | نعم (أرصدة الحسابات بعد كل عملية) | قبل `108ba4e` | محتاجة اعتماد محاسب (D-011) |
| القيود اليدوية وعكس القيود | مكتملة | `pages/JournalEntry.tsx` | نعم | قبل `108ba4e` | — |
| المصروفات والأصول والإهلاك وتسويات الكي-نت | مكتملة | `accounting/services/finance.py` | نعم | فلتر المصروفات بالشهر قبل `108ba4e` | — |
| ميزان المراجعة وقائمة الدخل والميزانية والإقفال | مكتملة | `accounting/` | نعم | قبل `108ba4e` | — |
| ملف وزارة التجارة XBRL | مكتملة جزئياً | `accounting/services/xbrl.py` | نعم | قبل `108ba4e` | محتاج مراجع حسابات قبل التقديم |
| التقارير ومقارنة الفروع | مكتملة | `pos/services/reports.py`، `pages/Reports.tsx` | نعم | جدول المقارنة (`bef797d`) | — |

### التطبيقات

| الوظيفة | الحالة | اختبار آلي | تجربة على السيرفر | لم يُختبر / نواقص |
|---|---|---|---|---|
| PWA العملاء على `<slug>.kuw1.com` | غير مؤكدة | `flutter test` في CI (النتيجة الأخيرة ما اتراجعتش في الجلسة دي) | الصفحة بتفتح على `my-kids.kuw1.com` و`mykids.kuw1.com` | **الدخول بالكود مش شغال**، لأن رقم الصالون مش متصل. الحجز من التطبيق ما اتجربش على `kuw1.com` |
| تطبيق Android وiOS العام | غير مؤكدة | — | APK اتبنى في CI في جلسة سابقة | مفيش حسابات متاجر. الـ IPA مش موقَّع |
| تطبيق خاص لكل صالون (D-014) | مكتملة جزئياً | — | APK `com.mykids.salon` اتبنى ووُقّع بمفتاح المنصة | ما اتنشرش. إضافة صالون بتتعمل بملف في المستودع مش من الشاشة |


---

## 4. قواعد العمل والقرارات

### مطبَّق في الكود

**المال:**
- `Decimal` و`numeric(18,3)` في الخلفية، والـ float مرفوض.
- الواجهة تحسب بالفلس كأعداد صحيحة (`frontend/src/money.ts`).

**القيود المحاسبية:**
- تُكتب فقط عبر `apps.accounting.services.posting.post_entry`.
- القيود المرحّلة والفواتير ثابتة بـ triggers في قاعدة البيانات (`pos_immutable`)، والتصحيح يكون بقيد عكسي.

**Idempotency:** كل POST مالي يحتاج header اسمه `Idempotency-Key`.

**الضريبة:** لا ضريبة قيمة مضافة، لأن الكويت ليس فيها VAT حالياً.

**الصلاحيات:**
- الصلاحية الفعلية = (صلاحيات الدور + الإضافات للشخص) − الصلاحيات المحذوفة منه.
- المالك له كل الصلاحيات دائماً.
- لا أحد يعطي صلاحية لا يملكها هو، ولا أحد يعدّل دوره أو صلاحياته بنفسه.
- تغيير الدور يمسح استثناءات الشخص.
- كل تغيير يُسجَّل في سجل التدقيق.

**النقاط:**
- الكسب على المدفوع فعلاً، مضروباً في مضاعف المستوى.
- المستوى يُحسب من إجمالي النقاط المكتسبة.
- الاستبدال خصم تسويقي بدون قيد محاسبي (D-011، مؤقت).

**الرسائل:**
- رسائل الخدمة (تأكيد وتذكير وإيصال وتقييم) تذهب لمن عنده `whatsapp_opt_in`.
- الرسائل التسويقية («وحشتنا» و«وقت الزيارة الجاية») تحتاج `marketing_opt_in` أيضاً.
- العملاء المستوردون لا يحصلون على موافقة تسويقية تلقائياً.

**الاشتراك:**
- التجديد في نفس يوم انتهاء الفترة الحالية.
- لو الفترة تنتهي آخر الشهر، التجديد يكون آخر كل شهر.
- لا إيقاف تلقائي للشركة: الحالة تتحول إلى `past_due` فقط.

**النطاقات:**
- أسماء محجوزة لا يأخذها أي صالون: `RESERVED_SUBDOMAINS` في الكود + `QASSA_RESERVED_SUBDOMAINS` في البيئة، وفيها أسماء تطبيقات أخرى على نفس السيرفر.
- الأسماء الفرعية على `kuw1.com` تعمل لأي باقة. الدومين الخاص مقصور على الباقات التي تسمح به.

### القرارات (التفاصيل في `docs/DECISIONS.md`)

| القرار | الموضوع |
|---|---|
| D-001 | النشر على المتاجر من حساب المنصة |
| D-002 / D-007 | واتساب غير رسمي (Evolution API)، ورقم لكل صالون |
| D-003 | الـ OTP عبر واتساب بدل SMS |
| D-004 | العمل على `main` |
| D-005 / D-015 / D-016 | نطاق لكل صالون، ولوحة الصالون على `/dashboard`، واختيار النطاق والمزامنة مع Coolify |
| D-006 | تطبيق العملاء: الدخول أولاً ثم الحجز |
| D-008 | التحقق بخطوتين للموظفين |
| D-009 | ملف XBRL |
| D-010 | فوترة الاشتراك يدوية، والموقع العام بطلب تواصل وبدون تسجيل ذاتي |
| D-011 | السياسات المحاسبية مؤقتة حتى يعتمدها محاسب |
| D-012 | رسائل الخدمة التلقائية |
| D-013 | الكاشير يعمل دون إنترنت |
| D-014 | تطبيق خاص لكل صالون من حساب الصالون، والمنصة عضو فيه |

**قرار من المحادثة:** صاحب المشروع اختار `kuw1.com` نطاقاً أساسياً، مع العلم بمخاطرة تعارض الأسماء مع تطبيقاته الأخرى (HR وfleet وdemo).

### اتُّفق عليه لكن لم يُنفَّذ (اقتراحات فقط)
- العربون في الحجز وسياسة عدم الحضور: يحتاج بوابة دفع.
- قائمة انتظار بالواتساب لصالونات الرجالي.
- كروت الهدايا، والأسعار حسب الوقت، وتارجت الموظفين.
- سؤال «توافق على عروضنا؟» في الكاشير أو في التسجيل، لجمع الموافقة التسويقية.
- تسجيل ذاتي للصالونات من الموقع.
- إضافة تطبيق صالون من الشاشة بدل الملف.
- انتهاء النقاط لكل نقطة على حدة بدل الانتهاء بعدم النشاط.

### يحتاج قراراً من صاحب المشروع
1. مزود الدفع (MyFatoorah أو Tap أو غيرهما).
2. محاسب يعتمد سياسات D-011.
3. مراجع حسابات قبل أي تقديم XBRL.
4. هل تبقى المزامنة التلقائية مع Coolify (D-016)؟ التوكن يتحكم في كل التطبيقات على السيرفر.
5. التقييم: هل نطلب تقييم Google من الجميع، أم من أصحاب 4-5 نجوم فقط كما هو الآن (review gating)؟
6. هل نحتاج تسجيلاً ذاتياً للصالونات؟
7. حسابات Google Play وApple وFirebase.
8. تغيير الاسم الفرعي `my-kids` إلى `mykids`؟ (يوجد الآن صالون منفصل اسمه `mykids` أنشأه صاحب المشروع).

---

## 5. قاعدة البيانات والتكاملات

**القاعدة:** PostgreSQL 16، وكل الجداول التي تخص شركة فيها `tenant_id`. الوصول عبر `Model.objects` مقيَّد بالشركة الحالية، و`Model.unscoped` استثناء صريح.

**الكيانات الرئيسية حسب التطبيق:**

| التطبيق | الكيانات |
|---|---|
| tenancy | Tenant، LegalEntity، Branch، Role، Membership (فيها `extra_permissions` و`denied_permissions`)، MembershipBranch، SalonSettings |
| identity | User، StaffOtp، TrustedDevice |
| platform | Plan، Subscription، TenantDomain، PlatformInvoice، SupportTicket، TicketMessage، Lead، SupportAccess، PlatformSettings |
| catalog | ServiceCategory، Service (فيها `upsell` و`rebook_days` و`art`)، ServicePrice |
| staff | StaffMember، StaffBranch، StaffSkill، CommissionEntry، WorkingHours، TimeOff |
| customers | Customer، Beneficiary (فيها `birth_date`)، OtpChallenge |
| booking | Appointment، AppointmentItem |
| pos | CashSession، Invoice، InvoiceLine، CreditNote، CreditNoteLine، Payment، PosDevice، OfflineSale |
| inventory | Product، StockLevel، StockMove، Supplier، GoodsReceipt، GoodsReceiptLine، SupplierBill، SupplierPayment |
| loyalty | PackagePlan، CustomerPackage، LoyaltySettings (فيها `tiers` والهدايا والانتهاء)، PointsEntry، Coupon |
| accounting | Account، AccountRoleMapping، FiscalYear، FiscalPeriod، JournalEntry، JournalLine، XbrlMapping، Expense، FixedAsset، ClearingSettlement، ReportVersion |
| notifications | WhatsAppChannel، WhatsAppMessage، MessagingSettings، Feedback |
| core | IdempotencyRecord، OutboxEvent، NumberSequence |
| audit | AuditLog |

**علاقات مهمة:**
- مفاتيح أجنبية مركّبة `(tenant_id, id)` عبر `apps.core.db.composite_tenant_fk` تمنع ربط كيان بكيان من شركة أخرى.
- `Customer` له عدة `Beneficiary` (أطفاله أو هو نفسه).
- `Invoice` تحتوي على `InvoiceLine`، وتولّد `JournalEntry`.

**الـ Migrations:**
- مكانها `backend/apps/*/migrations/` (61 ملف).
- التشغيل: `python manage.py migrate`.
- الإنتاج يشغّلها تلقائياً عند بدء الحاوية، ثم يشغّل `add_subdomains` و`e2e_users` (الأمر كاملاً في `docker-compose.prod.yml`).
- الفحص: `python manage.py makemigrations --check --dry-run` (موجود في CI).

**الـ API:**
- كل المسارات تحت `/api/v1/` (132 مسار في `backend/qassa/urls.py`).
- المواصفة: `docs/openapi.yaml`، وتتولد بـ `python manage.py spectacular`.
- الصفحة التفاعلية: `/api/docs/`.

**مجموعات المسارات:**

| المجموعة | المسارات |
|---|---|
| الدخول | `auth/*`: login، mfa، me، password set و forgot، csrf، devices |
| المنصة | `platform/*`: tenants، domains، owner-invite، subdomain-check، plans، invoices، tickets، leads، settings، dashboard |
| تنظيم الشركة | `org`، `org/branches`، `users`، `roles`، `salon-settings`، `subscription`، `support/*` |
| الخدمات والموظفون والعملاء | `catalog/*`، `staff/*`، `customers/*`، `beneficiaries/*`، `import/<kind>` |
| التشغيل | `booking/appointments*`، `pos/*` (sessions، checkout، quote، invoices، credit-notes، offline، devices، `invoices/<id>/whatsapp`)، `reports/*`، `export/<kind>` |
| المخزون والولاء | `inventory/*`، `loyalty/*`، `commissions` |
| المحاسبة | `accounting/*` |
| الواتساب والتقييم | `whatsapp`، `whatsapp/ready`، `whatsapp/auto-settings`، `whatsapp/<action>`، `feedback` |
| العامة (بدون دخول) | `public/salon`، `public/manifest`، `public/site`، `public/leads`، `public/feedback/<token>` |
| تطبيق العملاء | `app/*`: otp، register، me، catalog، slots، bookings |

**المصادقة:**
- **الموظفون:** جلسة Django مع CSRF، والتحقق بخطوتين للأدوار المالية والمالك، والشركة عبر `X-Tenant`، والصلاحيات من `required_permissions` في كل View.
- **فريق المنصة:** `IsPlatformStaff`.
- **العملاء:** token بعد OTP واتساب.

**الخدمات الخارجية:**

| الخدمة | الحالة |
|---|---|
| Evolution API (واتساب) | مضبوط في البيئة. رقم المنصة `Testapp` حالته غير معروفة، ولا يوجد رقم صالون متصل |
| Coolify API | اختياري (D-016)، وإعداداته موجودة |
| SMTP | **غير مضبوط** |
| Cloudflare (DNS) | يديره صاحب المشروع |
| GitHub Actions | CI والبناء |
| مزود الدفع | **لا يوجد** |

---

## 6. التشغيل والإعداد

**المتطلبات:** Python 3.13، وNode 22، وPostgreSQL 16، وRedis 7، وFlutter 3.47.8 لتطبيق الموبايل. أو Docker بدل كل ذلك.

**تشغيل محلي بـ Docker:**
```bash
docker compose up    # web: http://localhost:5173 , API: http://localhost:8000/api/docs/
```

**تشغيل محلي بدون Docker:**
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
python manage.py migrate
python manage.py seed_dev          # بيانات وهمية، يرفض التشغيل في الإنتاج
python manage.py runserver 8000
celery -A qassa worker -B -l info  # في terminal ثانٍ
cd ../frontend && npm install && npm run dev
```

**حسابات `seed_dev` المحلية:**
- الإيميلات بالنمط: `owner@mykids.dev`، و`cashier@mykids.dev`، و`branchmanager@mykids.dev`، و`accountant@mykids.dev`، و`financemanager@mykids.dev`. ونفس النمط لـ `gentle.dev` و`lamsa.dev`.
- كلمة المرور الافتراضية للتطوير مكتوبة في `README.md` وتطبعها `seed_dev`. تعمل محلياً فقط.

**الاختبارات والبناء:**
```bash
cd backend && pytest -p no:warnings                 # يحتاج PostgreSQL و Redis
python manage.py makemigrations --check --dry-run
python manage.py spectacular --file /tmp/o.yaml --validate --fail-on-warn
cd frontend && npx tsc -b && npx vitest run && npx vite build
cd mobile && flutter analyze && flutter test
```

**متغيرات البيئة** (القيم أمثلة شكلية فقط):

| المتغير | الوظيفة | مثال |
|---|---|---|
| `QASSA_ENV` | `development` أو `test` أو `staging` أو `production` | `staging` |
| `DJANGO_SECRET_KEY` | مفتاح Django | `<secret>` |
| `DJANGO_ALLOWED_HOSTS` | نطاقات المنصة، مفصولة بفواصل | `kuw1.com,www.kuw1.com,qassa.kuw1.com` |
| `PLATFORM_HOST` | نفس النطاقات لـ nginx، مفصولة بمسافات | `kuw1.com www.kuw1.com qassa.kuw1.com` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | | `https://kuw1.com,https://*.kuw1.com` |
| `QASSA_TENANT_BASE_DOMAIN` | أساس النطاقات الفرعية | `kuw1.com` |
| `QASSA_RESERVED_SUBDOMAINS` | أسماء محجوزة لتطبيقات أخرى | `demo,fleet,...` |
| `QASSA_PUBLIC_ADMIN_URL` | أساس لينكات الدعوة والتقييم | `https://kuw1.com` |
| `POSTGRES_*`، `REDIS_URL` | قاعدة البيانات والطوابير | |
| `QASSA_WHATSAPP_ADAPTER` | `evolution` أو `console` أو `disabled` | `evolution` |
| `QASSA_WHATSAPP_URL` و`QASSA_WHATSAPP_TOKEN` | البوابة ومفتاحها العام | `<secret>` |
| `QASSA_PLATFORM_WA_INSTANCE` | رقم المنصة (أكواد الموظفين والدعوات) | `<instance>` |
| `QASSA_SMTP_HOST`، `_PORT`، `_USER`، `_PASSWORD`، `QASSA_MAIL_FROM` | البريد (غير مضبوط حالياً) | |
| `COOLIFY_API_URL`، `COOLIFY_API_TOKEN`، `COOLIFY_APP_UUID`، `COOLIFY_WEB_SERVICE` | مزامنة النطاقات (D-016) | |
| `TRUSTED_PROXY_COUNT` | عدد البروكسيات قبل Django (2 في الإنتاج) | `2` |
| `THROTTLE_LOGIN`، `THROTTLE_PUBLIC`، `THROTTLE_LEAD` | حدود الطلبات | `10/min` |
| `QASSA_TRUSTED_DEVICE_DAYS` | مدة تذكّر الجهاز | |
| `QASSA_SALES_WHATSAPP`، `QASSA_SALES_EMAIL` | تواصل المبيعات | |
| `SEED_PASSWORD`، `SEED_STAFF_PHONE` | بيانات تجريبية على السيرفر التجريبي | `<secret>` |
| `E2E_PASSWORD` | حسابات الاختبار `e2e-owner@qassa.test` و`e2e-ops@qassa.test`. حذفه يعطّل الحسابين عند النشر التالي | `<secret>` |
| `QASSA_OTP_ECHO` | للتجربة فقط | `0` |
| `LOG_LEVEL` | | `INFO` |

**النشر الحالي:**
- Coolify، تطبيق `qassa`، من `docker-compose.prod.yml`، والفرع `main`.
- **الدفع إلى GitHub لا ينشر تلقائياً.** النشر يتم بزر **Deploy** في Coolify، أو تلقائياً عند إضافة نطاق (D-016).
- النطاقات تُضاف على خدمة **`web`** فقط، وليس على `backend`.
- **الإصدارات:** تغيير ملف `VERSION` على `main` يجعل `release.yml` ينشئ tag وRelease. الإصدار الحالي في الملف 0.2.0، وآخر tag هو `v0.2.0`.
- **PWA العملاء:** مبنية مسبقاً في `deploy/pwa`، عبر `deploy/build-pwa.sh` أو workflow `build-pwa.yml`، لأن السيرفر ARM واتصاله بطيء.

**الشبكة والشهادات:**
- DNS: سجل wildcard `*.kuw1.com` يشير للسيرفر. `kuw1.com` نفسه عليه بروكسي Cloudflare.
- Traefik يصدر شهادات Let's Encrypt لكل نطاق مضاف في Coolify.
- السيرفر بمعمارية ARM.

---

## 7. حالة المشروع الحالية

**ما أُنجز في آخر جلسات العمل:**
- مطابقة التصميم مع الريفرنس.
- مستويات النقاط والهدايا.
- تبويبات الإعدادات.
- التقييمات ورسائل «وحشتنا» و«وقت الزيارة الجاية».
- الاستيراد، والحاسبة، واقتراح الإضافة في الكاشير.
- الانتقال إلى `kuw1.com` و`/dashboard`.
- النطاقات وCoolify.
- لينك المالك، ودعوات المستخدمين.
- الإيصال على الواتساب.
- الصلاحيات الدقيقة.

**آخر ما كان يُعمل عليه:** الصلاحيات الدقيقة (`8dbf125`)، وقبلها إرسال الإيصال من رقم الصالون (`f8583c3`). **الاثنان غير منشورين.** السيرفر على `9676fc5`، تحقق منه عبر `https://kuw1.com/api/v1/version`.

**ملفات آخر تغييرين:**
- `backend/apps/tenancy/models.py`
- `backend/apps/tenancy/api/users.py`
- `backend/apps/tenancy/migrations/*member_permissions*`
- `backend/apps/identity/api/views.py`
- `frontend/src/pages/Users.tsx`
- `frontend/src/components/PermissionPicker.tsx`
- `backend/apps/notifications/api/views.py`
- `backend/apps/notifications/auto.py`
- `frontend/src/pages/Invoices.tsx`
- `backend/tests/test_permissions_control.py`

**أخطاء أو مشاكل معروفة:**
- **لا يوجد رقم واتساب صالون متصل**، فدخول العملاء بالكود لا يعمل. سجل My Kids فيه محاولة OTP فاشلة بسبب «company number not connected».
- **SMTP غير مضبوط**، فالدعوات ونسيت الباسورد تعتمد على واتساب أو اللينك اليدوي.
- **رقم المنصة `Testapp`:** حالته غير معروفة.
- **`docs/STATUS.md` قديم ويتعارض مع الواقع.** يقول إن مفتاح Evolution «منتظر»، والفحص أظهر أنه مضبوط في Coolify. أيضاً قلتُ لصاحب المشروع أكثر من مرة أن يضيف المفتاح، وكان ذلك خطأ مني.
- **حسابات `e2e` ما زالت مفعّلة على السيرفر** (`E2E_PASSWORD` موجود).
- **توكن Coolify القديم:** كُتب في المحادثة. استُبدل بتوكن جديد في البيئة، و**إلغاء القديم غير مؤكد**، لأن صاحب المشروع لا بد أن يحذفه من واجهة Coolify.

**أشياء جُرِّبت ولم تنجح:**
- **رفع tags من بيئة العمل:** مرفوض من الـ proxy، فحُلّ ذلك بـ `release.yml`.
- **اختبار حدود الطلبات على السيرفر:** الـ IP الخارج من بيئة العمل يتغير، فاختُبر بدلاً من ذلك بـ Redis حقيقي في الاختبارات.
- **إضافة نطاق على خدمة `backend` في Coolify:** لا يعمل (خطأ SSL). يجب إضافته على `web`.

**الاختبارات المشغَّلة فعلياً (2026-11-01):**

| الفحص | النتيجة |
|---|---|
| Backend `pytest` | **176 passed** |
| `makemigrations --check` | لا تغييرات |
| `spectacular --validate --fail-on-warn` | بلا تحذيرات |
| Frontend `tsc -b` | نجح |
| `vitest` | 8 passed |
| `vite build` | نجح |
| CI على GitHub لآخر commit (`8dbf125`) | success |
| فحوص متصفح على السيرفر | لصفحات النطاقات، و`/dashboard`، والكاشير، والعملاء، والتقييم، والواتساب، والحاسبة، والاستيراد (معاينة)، ولوحة المنصة. بدون أخطاء |
| فحص متصفح محلي | لشاشة الأدوار |

**لم يُشغَّل:**
- Flutter (`flutter analyze` و`test`) في هذه الجلسة. يعمل في CI عند تغيير `mobile/`، ونتيجته الأخيرة غير مُتحقق منها هنا.
- اختبار الكاشير دون إنترنت بعد نقل الـ service worker إلى `/_q/`.
- إرسال واتساب حقيقي، لعدم وجود رقم متصل.
- إنشاء شركة حقيقية بعد تفعيل D-016.

---

## 8. Git

| البند | القيمة |
|---|---|
| المستودع | `https://github.com/ammarnabileg/qassa` |
| الفرع | `main` (العمل كله عليه، D-004) |
| آخر commit للكود | `8dbf125` — "Permission control: editable and custom roles, per-person extra and removed permissions" |
| commits بعده | `233fd91` (أول نسخة من ملف التسليم)، ثم commit تحديث ملف التسليم. ملفات توثيق فقط، ومفيش فيها تغيير كود |
| المنشور على السيرفر | `9676fc5`، تحقق منه عبر `https://kuw1.com/api/v1/version` |
| الفرق بين `main` والسيرفر | commit-ين كود مش منشورين: `f8583c3` (إرسال الإيصال من رقم الصالون) و`8dbf125` (الصلاحيات الدقيقة). محتاجين Deploy من Coolify |
| تغييرات غير محفوظة | لا يوجد |
| Tags | `v0.1.0`، `v0.2.0` |
| طلبات الدمج | لا يوجد (العمل مباشر على `main`) |

**Commits:** بالإيميل المعتمد للمشروع، وتنتهي بسطري `Co-Authored-By` و`Claude-Session` إذا كانت من Claude.

---

## 9. خطة إكمال النظام

### أ. ضروري لتشغيل النظام

1. **نشر آخر نسخة**
   - **المطلوب:** Deploy من Coolify.
   - **الاعتماد:** لا شيء.
   - **التحقق:** `https://kuw1.com/api/v1/version` يعرض `8dbf125` أو أحدث، وتبويب «الأدوار» يظهر في شاشة المستخدمين.
2. **ربط رقم واتساب لكل صالون**
   - **المطلوب:** من `<slug>.kuw1.com/dashboard/whatsapp` ثم «ربط الرقم» ثم مسح الـ QR من موبايل الصالون.
   - **الاعتماد:** رقم مخصص للصالون.
   - **التحقق:** الحالة «مربوط»، وكود دخول يصل من تطبيق العملاء.
3. **التحقق من رقم المنصة `Testapp`**
   - **المطلوب:** فتحه في لوحة Evolution، وربطه إن لم يكن «open».
   - **التحقق:** كود التحقق بخطوتين يصل لحساب مالك عليه رقم.
4. **إلغاء توكن Coolify القديم**
   - **المطلوب:** من Coolify ← Keys & Tokens. يفعلها صاحب المشروع.
   - **التحقق:** أي طلب API بالتوكن القديم يرجع 401.
5. **تحديث `docs/STATUS.md`** ليطابق الواقع.
   - **التحقق:** لا تعارض مع هذا الملف.

### ب. ضروري قبل الاستخدام الفعلي

1. **إعداد SMTP**
   - **المطلوب:** متغيرات `QASSA_SMTP_*` في Coolify.
   - **التحقق:** «نسيت الباسورد» يرسل بريداً فعلياً.
2. **إنشاء الحسابات الحقيقية وتعطيل حسابات الاختبار**
   - **المطلوب:** إنشاء حسابات المالكين الحقيقية، ثم حذف `E2E_PASSWORD` و`SEED_PASSWORD` من Coolify.
   - **التحقق:** حسابات `e2e` لا تدخل.
3. **اعتماد السياسات المحاسبية (D-011)**
   - **المطلوب:** مراجعة مع محاسب.
   - **الملفات:** `accounting/services/posting.py`، `pos/services/ledger.py`، `docs/DECISIONS.md`.
   - **التحقق:** القرار يتغير من «مؤقت» إلى «معتمد».
4. **اختبار الكاشير دون إنترنت على السيرفر بعد نقل الـ service worker**
   - **الملفات:** `frontend/public/sw.js`، `frontend/src/main.tsx`.
   - **التحقق:** قطع الشبكة وبيع، ثم رجوع الشبكة ومزامنة، والإيصالات تظهر في «إيصالات أوفلاين».
5. **تجربة صالون حقيقي لمدة أسبوعين.**
   - **التحقق:** قائمة مشاكل موثقة ومعالجة.
6. **جمع الموافقة التسويقية**
   - **المطلوب:** سؤال في الكاشير أو في تسجيل التطبيق (لم يُنفذ).
   - **الملفات:** `pages/POS.tsx`، `mobile/lib/screens/login.dart`، `customers/api/*`.
   - **التحقق:** `marketing_opt_in` يُحفظ، ورسائل «وحشتنا» تصل للموافقين فقط.
7. **أول إنشاء شركة بعد تفعيل D-016**
   - **المطلوب:** التأكد أن النطاق يُضاف تلقائياً، أو تعطيل الميزة إن لم يُقبل خطر التوكن.
   - **التحقق:** النطاق يظهر في Coolify ويعمل بـ HTTPS خلال دقائق، و`OutboxEvent` بـ topic `coolify.domains` حالته `done`.

### ج. تحسينات لاحقة

1. **بوابة الدفع وعربون الحجز**
   - **الاعتماد:** قرار مزود الدفع.
   - **الملفات:** `pos/`، `booking/`، `platform/services/billing.py`، `PlatformConsole.tsx`.
2. **النشر على المتاجر**
   - **الاعتماد:** حسابات Apple وGoogle.
   - **الملفات:** `mobile/`، workflows.
3. **إضافة تطبيق صالون من لوحة المنصة بدل ملف `mobile/salons/*.json`.**
4. **كروت الهدايا، والأسعار حسب الوقت، وتارجت الموظفين، وقائمة الانتظار.**
5. **انتهاء النقاط لكل نقطة على حدة** (إن قرر صاحب المشروع ذلك).
6. **تسجيل ذاتي للصالونات** (يحتاج قراراً ودفعاً وتحققاً من البريد).

---

## 10. ابدأ من هنا

**اقرأ أولاً بهذا الترتيب:**
1. هذا الملف.
2. `README.md`، ففيه قواعد العمل الأساسية.
3. `docs/DECISIONS.md` من D-001 لـ D-016.
4. `docs/ARCHITECTURE.md`.
5. `backend/qassa/urls.py` و`frontend/src/App.tsx` كخريطة للنظام.

**أول خطوات الفحص والتشغيل:**
1. `git pull` على `main`، وتأكد أن آخر commit هو `8dbf125` أو أحدث.
2. شغّل PostgreSQL وRedis، ثم اتبع أوامر §6. تأكد أن `pytest` يعطي 176 passed أو أكثر، وأن `npx tsc -b && npx vitest run` ينجح.
3. شغّل `seed_dev` وافتح `http://localhost:5173` بحساب `owner@mykids.dev`.
4. اقرأ `https://kuw1.com/api/v1/version` لتعرف المنشور.

**المهمة التالية المقترحة بالتحديد:**
- بعد أن ينشر صاحب المشروع ويربط رقم واتساب My Kids:
  1. اختبر دورة كاملة على السيرفر: دخول عميل بكود واتساب ← حجز ← فاتورة في الكاشير ← إرسال الإيصال من رقم الصالون ← وصول رسالة التقييم بعد ساعتين.
  2. وثّق كل خلل تجده.
- بالتوازي: اختبر الكاشير دون إنترنت بعد نقل الـ service worker.

**اسأل صاحب المشروع قبل أي قرار مؤثر، خصوصاً:**
1. أي مزود دفع؟
2. هل نُبقي المزامنة التلقائية مع Coolify رغم أن التوكن يتحكم في كل التطبيقات؟
3. سياسة طلب تقييم Google: الجميع أم أصحاب 4-5 نجوم فقط؟
4. هل يوجد محاسب ومراجع حسابات، ومتى؟
5. هل نسمح بتسجيل ذاتي للصالونات؟
6. أي تغيير في القيود المحاسبية، أو في النطاقات وCoolify، أو في التطبيقات الأخرى على نفس السيرفر. **لا تلمس تطبيقات أخرى على Coolify.**
7. الأسماء الفرعية: هل يُغيَّر `my-kids`؟ وما أسماء التطبيقات الجديدة على `kuw1.com` التي يجب حجزها؟

**قواعد ثابتة:**
- لا أسرار في الكود ولا في المحادثات.
- لا تدّعِ نجاح دفع أو واتساب أو قيد محاسبي غير حقيقي.
- القيود المحاسبية مقترحة حتى يعتمدها محاسب.
- لا ترفع ملف XBRL الحقيقي.
- لا تربط MFA نيابة عن أحد.

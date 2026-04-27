# Souk-DZ Agent 🇩🇿

> وكيل آلي مجاني يراقب أكبر مواقع الإعلانات الجزائرية + فيسبوك + تيك توك،
> ويرسل لكِ يوميًا بالبريد الإلكتروني تقريرًا بأفضل الفرص الشرائية بسعر
> أقل من المعتاد لتعيدي بيعها بربح.

---

## 🇫🇷 Quick overview (English / Français)

Souk-DZ is a free, GitHub-Actions-driven scraper + price-arbitrage agent for the
Algerian market. Every morning at 06:00 Africa/Algiers it:

1. Pulls fresh listings from **Ouedkniss**, **Zerbote**, **Soukalys**,
   **PrixAlgerie** (classifieds with public prices), then from **Facebook**
   public Pages/Groups and **TikTok** hashtags as secondary signal.
2. Sends every listing through **Google Gemini (free tier)** to extract a
   canonical product name + brand + category and compute a stable
   `cluster_key` so identical products group together across sources.
3. Compares each listing to the median price of its cluster (fed by 30 days of
   historical data stored in SQLite) and flags any item priced at least
   25% below the median as an **opportunity**.
4. Emails you a beautiful HTML report + an Excel attachment with all listings
   and the ranked top opportunities.

Cost: **$0/month**.

---

## 🛠️ كيف يعمل (تقنياً)

```
┌─────────────────────────────────────────────────────────────┐
│  GitHub Actions cron (06:00 Africa/Algiers daily)            │
└────────────────────────────┬─────────────────────────────────┘
                             ▼
   ┌────────────────────┬────────────────────┬─────────────────┐
   │  Classified sites  │   Facebook public  │ TikTok hashtags │
   │  (Playwright +     │   pages + groups   │  + accounts     │
   │   httpx scrapers)  │   (mbasic.fb.com)  │                 │
   └────────────────────┴────────────────────┴─────────────────┘
                             ▼
                  Google Gemini (free tier)
              normalize → canonical name + cluster_key
                             ▼
                   SQLite history (30 days)
                             ▼
              Detect opportunities (≥25% below median)
                             ▼
            HTML email + Excel attachment via Gmail SMTP
```

---

## 🚀 طريقة التشغيل (إعداد سريع لمدة ~10 دقائق)

### 1. أنشئي حساب GitHub
لو ما عندكِ حساب: <https://github.com/signup> (مجاني تماماً).

### 2. عمل Fork لهذا المستودع
انقري على زر **Fork** أعلى يمين هذه الصفحة. هذا ينشئ نسخة خاصة بكِ.

### 3. الحصول على مفتاح Gemini API (مجاني)
1. ادخلي على <https://aistudio.google.com/apikey>
2. انقري **Create API key** ثم انسخي المفتاح.

### 4. إنشاء App Password لإرسال الإيميل من Gmail
1. فعّلي **التحقق بخطوتين** على حسابك إن لم يكن مفعلاً: <https://myaccount.google.com/security>
2. ادخلي على <https://myaccount.google.com/apppasswords>
3. اختاري **Mail** + **Other** → اكتبي "Souk-DZ" → انقري **Generate**.
4. انسخي الـ 16 حرفاً (بدون مسافات).

### 5. إضافة المفاتيح إلى GitHub Secrets
في صفحة الـ fork اللي عندكِ:
**Settings → Secrets and variables → Actions → New repository secret**

أنشئي هذه الأسرار **واحداً واحداً**:

| Name | Value |
|------|-------|
| `GEMINI_API_KEY`  | المفتاح من الخطوة 3 |
| `SMTP_HOST`       | `smtp.gmail.com` |
| `SMTP_PORT`       | `587` |
| `SMTP_USERNAME`   | بريدك الإلكتروني (Gmail) |
| `SMTP_PASSWORD`   | App Password من الخطوة 4 |
| `EMAIL_FROM`      | نفس بريدك (Gmail) |
| `EMAIL_TO`        | البريد الذي تريدين استلام التقرير عليه (يمكن أن يكون نفسه) |

### 6. تفعيل GitHub Actions
في الـ fork: **Actions** → انقري الزر الأخضر **"I understand my workflows, go ahead and enable them"**.

### 7. التشغيل اليدوي للاختبار
**Actions → Daily report → Run workflow → Run workflow**.

سترين التشغيل خلال 5-10 دقائق. لو نجح، سيصلكِ إيميل تلقائياً على `EMAIL_TO`.

> بعدها يعمل تلقائياً كل يوم 6 صباحاً بتوقيت الجزائر بدون تدخل منكِ.

---

## ⚙️ تخصيص المصادر

عدّلي الملف `config.yaml` لإضافة/إزالة:
- مجموعات Facebook (روابط `https://www.facebook.com/groups/<id>/`)
- صفحات Facebook (روابط `https://www.facebook.com/<page>/`)
- حسابات TikTok (مثل `@username`)
- فئات Ouedkniss
- نسبة الخصم لاكتشاف الفرص

ثم **Commit** التعديلات وستُطبَّق في التشغيل القادم.

---

## 🧪 التشغيل المحلي (للمطورين)

```bash
git clone https://github.com/<your-username>/souk-dz-agent.git
cd souk-dz-agent

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install --with-deps chromium

cp .env.example .env
# املئي القيم في .env

souk-dz check          # تأكدي من الإعدادات
souk-dz scrape ouedkniss --verbose
souk-dz run --dry-run  # تشغيل كامل بدون إرسال إيميل
souk-dz run            # تشغيل مع إرسال الإيميل
pytest                 # الاختبارات
```

---

## 📂 بنية المشروع

```
souk-dz-agent/
├── config.yaml                     # مصادر المراقبة (قابلة للتعديل)
├── pyproject.toml
├── README.md
├── .env.example
├── .github/workflows/daily-report.yml
└── souk_dz/
    ├── cli.py                      # سطر الأوامر
    ├── orchestrator.py             # خط الإنتاج الكامل
    ├── config.py
    ├── models.py                   # Pydantic models
    ├── scrapers/                   # 6 scrapers (مصدر لكل ملف)
    ├── ai/normalizer.py            # Gemini batched normalization
    ├── analysis/
    │   ├── database.py             # SQLite history
    │   └── opportunity.py          # كشف الفرص (median + threshold)
    └── reporting/
        ├── email_sender.py         # SMTP / Gmail
        ├── excel.py                # تقرير Excel
        └── templates/email.html.j2 # قالب الإيميل HTML
```

---

## ⚠️ تنبيهات مهمة

1. **هذا أداة جمع بيانات عامة فقط** — لا تستخدمها لإرسال رسائل آلية أو لأي شيء يخالف
   شروط Facebook/TikTok.
2. **الموثوقية متغيرة على Facebook/TikTok** — تتغير صفحاتهما بانتظام؛ قد تحتاج
   تحديثات بسيطة من وقت لآخر.
3. **لا توجد ضمانة ربح** — التقارير تساعدكِ على اكتشاف فرص، لكن البائع قد يكون
   أرخص لسبب (عيب، احتيال، إلخ). راجعي قبل الشراء.
4. **حد Gemini المجاني**: 1500 طلب/يوم. الوكيل مصمم ليبقى أقل بكثير من هذا الحد.
5. **حد GitHub Actions**: 2000 دقيقة/شهر. التشغيل اليومي ~8 دقائق ⇒ ~240 دقيقة/شهر.

---

## 📜 الترخيص

MIT — استخدام/تعديل/مشاركة بحرية.

# کاوش AI 2 (Kavosh AI 2)

اپلیکیشن وب فارسی‌محور با تم فضایی برای چت هوش مصنوعی، استودیو تصویر/ویدئو، تیکت، مسابقات، اشتراک و پنل کارکنان.

## پشته فنی

- **بک‌اند:** Python 3.11+ فقط با کتابخانهٔ استاندارد (`http.server`)
- **فرانت‌اند:** SPA با Vazirmatn و Inter، تم تیره/روشن، RTL/LTR
- **هوش مصنوعی:** OpenRouter — کلید فقط سمت سرور

## اجرا

```bash
python main.py
```

سپس http://localhost:3000

## متغیرهای محیطی

به `.env.example` مراجعه کنید. مهم‌ترین‌ها:

- `OPENROUTER_API_KEY` / `OPENROUTER_MODEL`
- `SITE_URL` / `SITE_NAME`
- `MANAGER_PASSWORD`
- `DEPUTY_1_PASSWORD` … `DEPUTY_8_PASSWORD`
- `TEACHER_1_PASSWORD` … `TEACHER_10_PASSWORD`
- `IMAGE_API_*` و `VIDEO_API_*` (اختیاری)

اگر سرویس پیکربندی نشده باشد، رابط پیام شفاف نشان می‌دهد و خروجی جعلی تولید نمی‌کند.

## نقش‌ها

یک مدیر، هشت معاون، ده معلم. ورود با `POST /api/auth/login` و Bearer token.
Google OAuth در این نسخهٔ stdlib فعال نیست و نیاز به ارائه‌دهندهٔ خارجی دارد.

## API

- GET /api/health
- POST /api/chat
- POST /api/auth/login | logout
- GET /api/me
- POST /api/panel/summary
- POST /api/image | /api/video

## زبان‌ها

۵۰ زبان در انتخابگر؛ متن کامل برای فارسی و انگلیسی. بقیه با نام بومی و جهت درست.

## استقرار Render

Build خالی، Start: `python main.py` یا از render.yaml

## صادقانه دربارهٔ محدودیت‌ها

| مورد | وضعیت |
|------|--------|
| ناوبری و داشبورد واکنش‌گرا | آماده |
| چت واقعی | با کلید OpenRouter |
| تصویر/ویدئو واقعی | فقط با API پیکربندی‌شده |
| تیکت/مسابقه/اشتراک UI | آماده؛ ذخیره محلی؛ پرداخت واقعی خیر |
| پنل کارکنان | با رمز محیطی |
| OAuth گوگل / درگاه پرداخت | نیاز به سرویس خارجی |

کلید واقعی را در گیت یا فرانت قرار ندهید.

## اصلاحات همسویی فرانت/بک‌اند

- `GET /api/me` برای حفظ ورود بعد از رفرش
- `GET /api/plans` ، `GET /api/contests` ، `GET /api/notifications` ، `GET /api/admin/summary`
- `POST /api/contests` و `POST /api/tickets` با کنترل نقش سمت سرور
- SQLite در `data/kavosh.db` با جداول sessions, plans, contests, tickets, notifications, activity_log, media_jobs
- محدودیت ورود: حداکثر ۸ تلاش در ۵ دقیقه برای هر IP
- تست: `python test_api.py`

Google OAuth، پرداخت واقعی و هماهنگ‌کنندهٔ چندمدلی فعال اعلام نمی‌شوند.

## پنل مدیریت امن (نسخه تکمیل‌شده)

### بررسی صادقانه
- فایل‌های `server.js` / `server(1).js` / `server(2).js` / `index(1).html` در مخزن/زیپ موجود **نیستند**.
- پروژهٔ واقعی روی **Python stdlib** (`main.py` + `public/index.html`) است؛ همان حفظ شد.

### امنیت ورود مدیر
- رمز فقط از `MANAGER_PASSWORD` روی سرور
- مقایسه با `hmac.compare_digest`
- محدودیت تلاش ورود (۸ بار / ۵ دقیقه / IP)
- نشست: کوکی `kavosh_session` با **HttpOnly**، **SameSite=Lax**، و **Secure** وقتی درخواست از HTTPS/`X-Forwarded-Proto: https` باشد
- CSRF برای `POST /api/admin/test-connection`
- خروج نشست را از حافظه، SQLite و کوکی پاک می‌کند

### APIهای مدیریتی
- `GET /api/admin/summary`
- `GET /api/admin/providers` — وضعیت مدل/ارائه‌دهنده **بدون** کلید
- `GET /api/admin/csrf`
- `POST /api/admin/test-connection` — آزمایش چت OpenRouter یا بررسی تنظیم تصویر/ویدئو

### Render
در سرویس Web → Environment این‌ها را بگذارید (بعد از تغییر معمولاً **Manual Deploy** لازم است):
- `MANAGER_PASSWORD`
- `OPENROUTER_API_KEY` / `OPENROUTER_MODEL`
- `SITE_URL` / `SITE_NAME`
- اختیاری: `IMAGE_*` و `VIDEO_*` و رمز معاون/معلم

این برنامه متغیرهای Render را از داخل تغییر نمی‌دهد.

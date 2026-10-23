"""Kavosh AI 2 - Python standard-library server."""
from __future__ import annotations
import ast, base64, json, math, os, re, secrets, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'
PORT = int(os.getenv('PORT', '3000'))
API_KEY = os.getenv('OPENROUTER_API_KEY', '').strip()
MODEL = os.getenv('OPENROUTER_MODEL', 'openrouter/auto').strip()
SITE_URL = os.getenv('SITE_URL', 'https://example.com').strip()
SITE_NAME = os.getenv('SITE_NAME', 'Kavosh AI 2').strip()
WINDOW_SECONDS, MAX_REQUESTS = 60, 20
buckets: dict[str, list[float | int]] = {}
sessions: dict[str, dict[str, object]] = {}
lock = threading.Lock()


def json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False).encode('utf-8')


def normalize_digits(value: str) -> str:
    # Explicit replacements avoid any dependency on locale.
    value = value.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789'))
    value = value.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789'))
    return value.replace('٫', '.').replace('−', '-').replace('–', '-').replace('×', '*').replace('÷', '/').replace('٪', '%')


def safe_math(expression: str):
    expr = normalize_digits(expression).replace(',', '.').replace('^', '**').strip()
    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError as exc:
        raise ValueError('عبارت ریاضی معتبر نیست') from exc
    def calc(node):
        if isinstance(node, ast.Expression): return calc(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool): return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            n = calc(node.operand); return n if isinstance(node.op, ast.UAdd) else -n
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow)):
            a, b = calc(node.left), calc(node.right)
            if isinstance(node.op, (ast.Div, ast.Mod)) and b == 0: raise ValueError('تقسیم بر صفر تعریف نشده است')
            if isinstance(node.op, ast.Add): result = a+b
            elif isinstance(node.op, ast.Sub): result = a-b
            elif isinstance(node.op, ast.Mult): result = a*b
            elif isinstance(node.op, ast.Div): result = a/b
            elif isinstance(node.op, ast.Mod): result = a%b
            else:
                if abs(b) > 1000 or abs(a) > 1e100: raise ValueError('توان بیش از حد بزرگ است')
                result = a**b
            if not math.isfinite(result): raise ValueError('نتیجه معتبر نیست')
            return result
        raise ValueError('عبارت ریاضی معتبر نیست')
    return calc(tree)


def solve_math(text: str):
    s = normalize_digits(text).strip()
    s = re.sub(r'^(?:حاصل|محاسبه کن|حساب کن|جواب|solve|calculate)\s*[:：]?\s*', '', s, flags=re.I)
    s = re.sub(r'[؟?=]+$', '', s).strip()
    if not s or not re.search(r'[+*/^%]|\d\s*-\s*\d', s) or not re.fullmatch(r'[\d\s().,+\-*/%^eE]+', s): return None
    try:
        n = safe_math(s)
        return f'پاسخ: {float(f"{n:.12g}")}'
    except ValueError as exc:
        return f'خطای ریاضی: {exc}'
    except (OverflowError, ZeroDivisionError):
        return 'خطای ریاضی: نتیجه معتبر نیست'


def call_json_api(url: str, key: str, payload: dict, timeout=45, extra_headers=None):
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    headers.update(extra_headers or {})
    request = Request(url, data=json_bytes(payload), headers=headers, method='POST')
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(2_000_000)
            return response.status, json.loads(raw.decode('utf-8'))
    except HTTPError as exc:
        raw = exc.read(1_000_000)
        try: data = json.loads(raw.decode('utf-8'))
        except Exception: data = {}
        return exc.code, data
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError('ارتباط با سرویس بیرونی برقرار نشد؛ تنظیمات یا اتصال را بررسی کن.') from exc


def media_config(kind):
    prefix = 'IMAGE' if kind == 'تصویر' else 'VIDEO'
    return (os.getenv(f'{prefix}_API_URL', '').strip(), os.getenv(f'{prefix}_API_KEY', '').strip(), os.getenv(f'{prefix}_MODEL', '').strip())


def call_media(kind, prompt):
    endpoint, key, model = media_config(kind)
    if not endpoint or not key or not model:
        names = 'IMAGE_API_URL، IMAGE_API_KEY و IMAGE_MODEL' if kind == 'تصویر' else 'VIDEO_API_URL، VIDEO_API_KEY و VIDEO_MODEL'
        raise ValueError(f'برای ساخت {kind} باید {names} در تنظیمات خصوصی سرور تنظیم شوند. این سرویس پیش‌فرض فعال نیست.')
    if urlparse(endpoint).scheme not in ('https', 'http'):
        raise ValueError('آدرس API رسانه معتبر نیست.')
    status, data = call_json_api(endpoint, key, {'model': model, 'prompt': prompt}, timeout=90)
    if status < 200 or status >= 300:
        err = (data.get('error') or {}).get('message') if isinstance(data.get('error'), dict) else data.get('error')
        raise RuntimeError(str(err or data.get('message') or f'خطای سرویس رسانه ({status})'))
    items = data.get('data') or []
    first = items[0] if items and isinstance(items[0], dict) else {}
    output = data.get('output')
    output_url = output[0].get('url') if isinstance(output, list) and output and isinstance(output[0], dict) else None
    media_url = first.get('url') or output_url or data.get('url') or (data.get('video') or {}).get('url') or (data.get('image') or {}).get('url')
    b64 = first.get('b64_json') or data.get('b64_json')
    task_id = data.get('id') or data.get('task_id') or data.get('job_id')
    if media_url: return {'ok': True, 'url': media_url, 'taskId': task_id, 'provider': 'configured-media-api'}
    if b64 and kind == 'تصویر': return {'ok': True, 'dataUrl': 'data:image/png;base64,' + b64, 'taskId': task_id, 'provider': 'configured-media-api'}
    if task_id: return {'ok': True, 'taskId': task_id, 'status': data.get('status', 'submitted'), 'message': 'درخواست ثبت شد؛ برای دریافت نتیجه ممکن است API بررسی وضعیت لازم باشد.'}
    raise RuntimeError('قالب پاسخ این ارائه‌دهنده با نسخهٔ فعلی سازگار نیست.')


class Handler(BaseHTTPRequestHandler):
    server_version = 'KavoshAI2-Python'
    def log_message(self, fmt, *args):
        # Avoid logging query payloads or secrets.
        print('%s - %s' % (self.client_address[0], fmt % args))

    def send_json(self, status, obj):
        body = json_bytes(obj)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers(); self.wfile.write(body)

    def read_json(self, limit=100_000):
        length = int(self.headers.get('Content-Length', '0') or '0')
        if length > limit: raise ValueError('متن درخواست بیش از حد طولانی است.')
        raw = self.rfile.read(length) if length else b'{}'
        try: result = json.loads(raw.decode('utf-8'))
        except Exception as exc: raise ValueError('درخواست JSON معتبر نیست.') from exc
        if not isinstance(result, dict): raise ValueError('ساختار درخواست معتبر نیست.')
        return result

    def rate_allowed(self):
        ip = self.headers.get('X-Forwarded-For', self.client_address[0]).split(',')[0].strip()
        now = time.time()
        with lock:
            b = buckets.get(ip)
            if not b or now - float(b[0]) > WINDOW_SECONDS: b = [now, 0]
            b[1] = int(b[1]) + 1; buckets[ip] = b
            for k in list(buckets):
                if now - float(buckets[k][0]) > WINDOW_SECONDS: buckets.pop(k, None)
            return int(b[1]) <= MAX_REQUESTS

    def session(self):
        token = re.sub(r'^Bearer\s+', '', self.headers.get('Authorization', ''), flags=re.I).strip()
        with lock:
            s = sessions.get(token)
            if not s: return None
            if time.time() - float(s['created']) > 8*60*60:
                sessions.pop(token, None); return None
            return s

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/health':
            image = all(media_config('تصویر')); video = all(media_config('ویدئو'))
            return self.send_json(200, {'ok': True, 'name': 'Kavosh AI 2', 'version': '2.0.0', 'provider': 'openrouter', 'runtime': 'python', 'keyConfigured': bool(API_KEY), 'imageConfigured': image, 'videoConfigured': video, 'managerConfigured': bool(os.getenv('MANAGER_PASSWORD')), 'deputiesConfigured': sum(bool(os.getenv(f'DEPUTY_{i}_PASSWORD') or (i == 1 and os.getenv('DEPUTY_PASSWORD'))) for i in range(1, 9)), 'deputyCount': 8, 'teachersConfigured': sum(bool(os.getenv(f'TEACHER_{i}_PASSWORD')) for i in range(1, 11)), 'teacherCount': 10})
        if path == '/api/panel/summary':
            s = self.session()
            if not s: return self.send_json(401, {'ok': False, 'error': 'ابتدا وارد پنل شو.'})
            return self.send_json(200, {'ok': True, 'role': s['role'], 'site': SITE_NAME, 'version': '2.0.0', 'aiConfigured': bool(API_KEY), 'imageConfigured': all(media_config('تصویر')), 'videoConfigured': all(media_config('ویدئو')), 'note': 'این داشبورد فعلاً وضعیت سرویس را نشان می‌دهد؛ مدیریت دانش‌آموزان یا نمره‌ها پیاده‌سازی نشده است.'})
        if path == '/': path = '/index.html'
        if path == '/index.html':
            try: body = (PUBLIC / 'index.html').read_bytes()
            except OSError: return self.send_json(500, {'ok': False, 'error': 'فایل صفحه پیدا نشد.'})
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(body))); self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(body); return
        return self.send_json(404, {'ok': False, 'error': 'مسیر پیدا نشد.'})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/panel/summary':
            s = self.session()
            if not s: return self.send_json(401, {'ok': False, 'error': 'ابتدا وارد پنل شو.'})
            return self.send_json(200, {'ok': True, 'role': s['role'], 'site': SITE_NAME, 'version': '2.0.0', 'aiConfigured': bool(API_KEY), 'imageConfigured': all(media_config('تصویر')), 'videoConfigured': all(media_config('ویدئو')), 'note': 'این داشبورد فعلاً وضعیت سرویس را نشان می‌دهد؛ مدیریت دانش‌آموزان یا نمره‌ها پیاده‌سازی نشده است.'})
        if path == '/api/auth/login':
            try:
                body = self.read_json(5000); role = str(body.get('role', '')); password = str(body.get('password', ''))
                env_name = 'MANAGER_PASSWORD' if role == 'manager' else (f'DEPUTY_{role[6:]}_PASSWORD' if re.fullmatch(r'deputy[1-8]', role) else 'DEPUTY_PASSWORD' if role == 'deputy' else (f'TEACHER_{role[7:]}_PASSWORD' if re.fullmatch(r'teacher(?:[1-9]|10)', role) else ''))
                expected = os.getenv(env_name, '') if env_name else ''
                if not expected: return self.send_json(503, {'ok': False, 'error': 'رمز این نقش هنوز در تنظیمات خصوصی سرور تنظیم نشده است.'})
                import hmac
                if not hmac.compare_digest(password.encode(), expected.encode()): return self.send_json(401, {'ok': False, 'error': 'رمز عبور درست نیست.'})
                token = secrets.token_hex(32)
                with lock: sessions[token] = {'role': role, 'created': time.time()}
                return self.send_json(200, {'ok': True, 'token': token, 'role': role, 'expiresIn': 28800})
            except ValueError as exc: return self.send_json(400, {'ok': False, 'error': str(exc)})
        if path == '/api/auth/logout':
            token = re.sub(r'^Bearer\s+', '', self.headers.get('Authorization', ''), flags=re.I).strip()
            with lock: sessions.pop(token, None)
            return self.send_json(200, {'ok': True})
        if path in ('/api/image', '/api/video'):
            if not self.rate_allowed(): return self.send_json(429, {'ok': False, 'error': 'درخواست‌ها زیاد شده‌اند؛ کمی بعد دوباره تلاش کن.'})
            try:
                body = self.read_json(12000); prompt = str(body.get('prompt', '')).strip()[:4000]
                if not prompt: return self.send_json(400, {'ok': False, 'error': 'توضیح خروجی را بنویس.'})
                return self.send_json(200, call_media('تصویر' if path.endswith('/image') else 'ویدئو', prompt))
            except (ValueError, RuntimeError) as exc: return self.send_json(500, {'ok': False, 'error': str(exc)[:500]})
        if path == '/api/chat':
            if not self.rate_allowed(): return self.send_json(429, {'ok': False, 'error': 'درخواست‌ها خیلی زیاد شده‌اند؛ یک دقیقه بعد دوباره تلاش کن.'})
            try:
                body = self.read_json(); message = str(body.get('message', '')).strip()[:8000]
                if not message: return self.send_json(400, {'ok': False, 'error': 'اول پیامت را بنویس.'})
                math_answer = solve_math(message)
                if math_answer: return self.send_json(200, {'ok': True, 'answer': math_answer, 'provider': 'math'})
                if not API_KEY: return self.send_json(500, {'ok': False, 'error': 'کلید API تنظیم نشده است. OPENROUTER_API_KEY را در تنظیمات خصوصی سرور وارد کن.'})
                hist = body.get('history', [])
                if not isinstance(hist, list): hist = []
                messages = [{'role': 'system', 'content': 'You are Kavosh AI 2, a helpful Persian-first AI assistant. Answer in the language used by the user. Be accurate, clear, age-appropriate, and honest about uncertainty.'}]
                for item in hist[-18:]:
                    if isinstance(item, dict) and item.get('role') in ('user', 'assistant') and isinstance(item.get('content'), str): messages.append({'role': item['role'], 'content': item['content'][:8000]})
                messages.append({'role': 'user', 'content': message})
                status, data = call_json_api('https://openrouter.ai/api/v1/chat/completions', API_KEY, {'model': MODEL, 'messages': messages[-20:], 'temperature': .5, 'max_tokens': 1600}, extra_headers={'HTTP-Referer': SITE_URL, 'X-Title': SITE_NAME})
                if status < 200 or status >= 300:
                    err = (data.get('error') or {}).get('message') if isinstance(data.get('error'), dict) else data.get('error')
                    return self.send_json(500, {'ok': False, 'error': str(err or f'خطای سرویس هوش مصنوعی ({status})')[:500]})
                answer = ((data.get('choices') or [{}])[0].get('message') or {}).get('content')
                if not isinstance(answer, str) or not answer.strip(): return self.send_json(500, {'ok': False, 'error': 'پاسخ خالی از سرویس دریافت شد.'})
                return self.send_json(200, {'ok': True, 'answer': answer.strip(), 'provider': 'openrouter'})
            except ValueError as exc: return self.send_json(400, {'ok': False, 'error': str(exc)[:500]})
            except (RuntimeError, TimeoutError, OSError) as exc: return self.send_json(500, {'ok': False, 'error': str(exc)[:500]})
        return self.send_json(404, {'ok': False, 'error': 'مسیر پیدا نشد.'})


def main():
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    print(f'Kavosh AI 2 Python server listening on port {PORT}')
    server.serve_forever()

if __name__ == '__main__': main()

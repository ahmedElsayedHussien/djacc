import logging
from django.core.cache import cache
from django.http import HttpResponseForbidden
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

class BruteForceProtectionMiddleware(MiddlewareMixin):
    """
    Middleware to protect login endpoints from brute-force attacks.
    Uses RAM (Cache) for zero database footprint and ultra-fast performance.
    """
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_TIME_SECONDS = 900  # 15 minutes
    PROTECTED_PATHS = ['/accounts/login/', '/admin/login/']

    def process_request(self, request):
        if request.path in self.PROTECTED_PATHS and request.method == 'POST':
            ip = self.get_client_ip(request)
            cache_key = f'brute_force_{ip}'
            attempts = cache.get(cache_key, 0)
            
            if attempts >= self.MAX_FAILED_ATTEMPTS:
                logger.warning(f"Brute force attempt blocked from IP: {ip}")
                html_content = """
                <!DOCTYPE html>
                <html lang="ar" dir="rtl">
                <head>
                    <meta charset="UTF-8">
                    <title>تم حظر الوصول (Access Denied)</title>
                    <style>
                        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; padding: 100px; background-color: #f8f9fa; color: #333; }
                        h1 { color: #dc3545; font-size: 40px; margin-bottom: 10px; }
                        p { font-size: 20px; color: #555; }
                        .lock-icon { font-size: 80px; margin-bottom: 20px; }
                        .timer { font-weight: bold; color: #dc3545; }
                    </style>
                </head>
                <body>
                    <div class="lock-icon">🔒</div>
                    <h1>تم حظر عنوانك مؤقتاً</h1>
                    <p>لقد تجاوزت الحد الأقصى لمحاولات تسجيل الدخول الخاطئة (5 محاولات).</p>
                    <p>نظام الحماية من الاختراق (Anti-Bruteforce) قام بتجميد محاولاتك لدواعي أمنية.</p>
                    <p>يرجى المحاولة مرة أخرى بعد <span class="timer">15 دقيقة</span>.</p>
                </body>
                </html>
                """
                return HttpResponseForbidden(html_content)

    def process_response(self, request, response):
        if request.path in self.PROTECTED_PATHS and request.method == 'POST':
            ip = self.get_client_ip(request)
            cache_key = f'brute_force_{ip}'
            
            # 200 OK generally means the login page re-rendered with form validation errors
            if response.status_code == 200:
                attempts = cache.get(cache_key, 0)
                cache.set(cache_key, attempts + 1, timeout=self.LOCKOUT_TIME_SECONDS)
            # 302 Found generally means a successful redirect after login
            elif response.status_code == 302:
                cache.delete(cache_key)
                
        return response

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

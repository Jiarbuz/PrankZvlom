import os
import time
import ipaddress
import requests
import threading
import logging
import json
import uuid
from flask import redirect, url_for
from flask import Flask, request, abort, session, make_response, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from user_agents import parse
from redis import Redis
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from datetime import datetime, timedelta
from functools import lru_cache

# --- Логирование ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

# --- Конфигурация ---
bot_token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "8251275057:AAEb2Xt_v4eJUuM3H1FCDvU6yqAwd5H2WlY"
chat_id = os.getenv("TELEGRAM_CHAT_ID") or "-1002796496801"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'super-secret-key')
ENV = os.getenv("FLASK_ENV", "development")

BLOCKED_RANGES = [("104.16.0.0", "104.31.255.255")]  # пример
BLOCKED_IPS_FILE = "blocked_ips.json"
BLOCK_DURATION = 6 * 3600  # 6 часов

MAX_REQUESTS = 20
WINDOW_SECONDS = 30
BLOCK_TIME = 3600  # 1 час блокировки

blocked_ips = {}
ip_request_times = {}



# --- Логгер URL и токен ---
LOGGER_URL = "https://prankzvon.ru/"  # заменить на реальный URL
LOGGER_ACCESS_TOKEN = os.getenv("LOGGER_ACCESS_TOKEN")

# --- Redis ---
if ENV == "production":
    redis_url = os.getenv("REDIS_URL", "redis://user:pass@host:6379")
else:
    redis_url = "redis://localhost:6379"

def check_redis(url):
    try:
        r = Redis.from_url(url)
        if r.ping():
            logger.info(f"Redis connected: {url}")
            return True
        return False
    except Exception as e:
        logger.error(f"Redis error: {e}")
        return False

redis_client = Redis.from_url(redis_url) if check_redis(redis_url) else None
if not redis_client:
    logger.warning("Redis not available, using in-memory storage")

# --- Flask ---
app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=1),
)

env = os.getenv("FLASK_ENV", "development")
redis_url = (
    "redis://red-d23qvvumcj7s739luqo0:uB5xnzFoWjSAJSlF7gozCjARDba0Fhdt@red-d23qvvumcj7s739luqo0:6379"
    if env == "production"
    else "redis://localhost:6379"
)

def check_redis(url):
    try:
        r = Redis.from_url(url)
        if r.ping():
            logger.info(f"Redis connection established: {url}")
            return True
        return False
    except Exception as e:
        logger.error(f"Redis connection error: {str(e)}")
        return False

redis_client = None
if check_redis(redis_url):
    redis_client = Redis.from_url(redis_url)
else:
    redis_url = "memory://"
    logger.warning("Using memory storage as Redis is unavailable")

# Исправленная инициализация Limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri=redis_url if redis_client else "memory://",
    default_limits=["200 per day", "50 per hour"],
    strategy="fixed-window"
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8430330790:AAG1YWeiP2f1GaLP4J6XEQ0FDjk0wlvRWWA")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6330358945")

last_telegram_send = 0
last_log_message = None  # Изменили _last_log_message на last_log_message

# --- Блокировка IP ---
def load_blocked_ips():
    global blocked_ips
    try:
        with open(BLOCKED_IPS_FILE, "r") as f:
            data = json.load(f)
            now = time.time()
            blocked_ips = {ip: t for ip, t in data.items() if now < t}
            logger.info(f"Loaded blocked IPs: {len(blocked_ips)}")
    except Exception:
        blocked_ips = {}

def save_blocked_ips():
    try:
        with open(BLOCKED_IPS_FILE, "w") as f:
            json.dump(blocked_ips, f)
    except Exception as e:
        logger.error(f"Failed to save blocked IPs: {e}")

def get_client_ip():
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"

def ip_in_range(ip, ip_range):
    try:
        ip_obj = ipaddress.ip_address(ip)
        start = ipaddress.ip_address(ip_range[0])
        end = ipaddress.ip_address(ip_range[1])
        return start <= ip_obj <= end
    except Exception:
        return False

@lru_cache(maxsize=1024)
def get_ip_info(ip):
    try:
        resp = requests.get(f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,regionName,city,isp", timeout=3)
        data = resp.json()
        if data.get("status") == "success":
            return {
                "country": data.get("country", ""),
                "countryCode": data.get("countryCode", ""),
                "region": data.get("regionName", ""),
                "city": data.get("city", ""),
                "isp": data.get("isp", ""),
                "ip": ip
            }
    except Exception as e:
        logger.error(f"IP info error: {e}")
    return {}


_last_telegram_send = 0
def send_telegram_message(text):
    global last_telegram_send

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not set - message not sent")
        return False

    now = time.time()
    elapsed = now - last_telegram_send
    if elapsed < 1:
        time.sleep(1 - elapsed)

    last_telegram_send = time.time()

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML"
            },
            timeout=15
        )
        logger.info(f"Telegram API response status: {response.status_code}")
        logger.info(f"Telegram API response text: {response.text}")
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram send error: {str(e)}")
        return False

@app.before_request
def security_checks():
    if request.path.startswith("/static/"):
        return

    load_blocked_ips()
    ip = get_client_ip()
    now = time.time()

    # Проверка заблокированных диапазонов
    if any(ip_in_range(ip, r) for r in BLOCKED_RANGES):
        logger.info(f"Blocked IP by range: {ip}")
        abort(403)

    # Проверка заблокированных IP
    if ip in blocked_ips and blocked_ips[ip] > now:
        logger.info(f"Blocked IP by list: {ip}")
        abort(403)
    elif ip in blocked_ips:
        del blocked_ips[ip]
        save_blocked_ips()

    # Лимит по IP
    times = ip_request_times.get(ip, [])
    times = [t for t in times if now - t < WINDOW_SECONDS]
    times.append(now)
    ip_request_times[ip] = times

    if len(times) > MAX_REQUESTS:
        blocked_ips[ip] = now + BLOCK_TIME
        save_blocked_ips()
        info = get_ip_info(ip)
        msg = (
            f"⏰ Время: {datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"🌐 IP: {info.get('ip', ip)}\n"
            f"📍 Локация: {info.get('city', 'Unknown')}, {info.get('country', 'Unknown')}\n"
            f"📊 Запросов: {len(times)}/{MAX_REQUESTS}\n"
            f"🚫 IP заблокирован за превышение лимита."
        )
        threading.Thread(target=send_telegram_message, args=(msg,)).start()
        abort(429)

    # Лимит по client_id cookie
    client_id = request.cookies.get("client_id")
    if not client_id:
        client_id = str(uuid.uuid4())

    if not hasattr(app, "client_request_times"):
        app.client_request_times = {}

    ctimes = app.client_request_times.get(client_id, [])
    ctimes = [t for t in ctimes if now - t < WINDOW_SECONDS]
    ctimes.append(now)
    app.client_request_times[client_id] = ctimes

    if len(ctimes) > MAX_REQUESTS:
        logger.info(f"Blocked client_id {client_id} by cookie rate limit")
        abort(429)

    # Логирование посещений
    global last_log_message
    if request.path != "/log":
        ua = parse(request.headers.get("User-Agent", ""))
        log_msg = (
            f"🌍 Новый посетитель\n"
            f"📡 IP: {ip}\n"
            f"🖥 OS: {ua.os.family}\n"
            f"🌐 Браузер: {ua.browser.family}\n"
            f"🔗 Страница: {request.path}"
        )
        if log_msg != last_log_message:
            last_log_message = log_msg
            threading.Thread(target=send_telegram_message, args=(log_msg,)).start()

# Пример словаря переводов
translations = {
    'ru': {
        'info_title': "PrankVzlom 📹📔",
        'disclaimer': "САЙТ СДЕЛАН ДЛЯ РАЗВЛЕКАТЕЛЬНЫХ ЦЕЛЕЙ И МЫ НИКОГО НЕ ХОТИМ ОСКОРБИТЬ ИЛИ УНИЗИТЬ",
        'software': "Софты",
        'admins': "Администрация",
        'partners': "Партнёры",
        'main_admin': "Главный администратор",
        'creators': "Создатели",
        'senior_admins': "Старшие администраторы",
        'junior_admins': "Младшие администраторы",
        'senior_mods': "Старшие модераторы",
        'junior_mods': "Младшие модераторы",
        'junior_jr': "Новички",
        'copyright': "© 2025 PrankVzlom. Все права защищены.",
        'accept': "Принять",
        'modal_title': "ВНИМАНИЕ",
        'modal_content': "Этот сайт создан исключительно в развлекательных целях. Мы не хотим никого оскорбить или унизить.",
        'links': {
            'official_channel': "ОФИЦИАЛЬНЫЙ КАНАЛ",
            'redirect': "ПЕРЕХОДНИК",
            'chat': "ЧАТ",
            'tutorial': "ТУТОРИАЛ ПО КАМЕРАМ",
            'audio': "АУДИО КАНАЛ",
            'bot': "БОТ",
            'tiktok': "ТИК ТОК",
            'support': "ПОДДЕРЖКА"
        },
        'partner_owl': "Скоро..."
    },
    'en': {
        'info_title': "PrankVzlom 📹📔",
        'disclaimer': "THIS SITE IS FOR ENTERTAINMENT PURPOSES ONLY AND WE DON'T WANT TO OFFEND OR HUMILIATE ANYONE",
        'software': "Software",
        'admins': "Administration",
        'partners': "Partners",
        'main_admin': "Main Admin",
        'creators': "Creators",
        'senior_admins': "Senior Admins",
        'junior_admins': "Junior Admins",
        'senior_mods': "Senior Moderators",
        'junior_mods': "Junior Moderators",
        'junior_jr': "Newbies",
        'copyright': "© 2025 PrankVzlom. All rights reserved.",
        'accept': "Accept",
        'modal_title': "WARNING",
        'modal_content': "This site is made for entertainment purposes only. We don't want to offend or humiliate anyone.",
        'links': {
            'official_channel': "OFFICIAL CHANNEL",
            'redirect': "REDIRECT",
            'chat': "CHAT",
            'tutorial': "CAMERA TUTORIAL",
            'audio': "AUDIO CHANNEL",
            'bot': "BOT",
            'tiktok': "TIKTOK",
            'support': "SUPPORT"
        },
        'partner_owl': "Soon..."
    }
}


@app.route('/')
@limiter.limit("10 per minute")
def index():
    lang = session.get('lang', 'ru')
    t = translations[lang]
    
    data = {
        "info": {
            "title": t['info_title'],
            "description": t['disclaimer'],
            "links": [
                {"name": t['links']['official_channel'], "url": "https://t.me/+K7nGKPBpyIswMDhi"},
                {"name": t['links']['redirect'], "url": "https://t.me/PrankVZ"},
                {"name": t['links']['chat'], "url": "https://t.me/+gUAplPwH9GhiMDg1"},
                {"name": t['links']['tutorial'], "url": "https://t.me/+cpSOIonR_4cwMWEx"},
                {"name": t['links']['audio'], "url": "https://t.me/+Egx6krEx0zM3NTRl"},
                {"name": t['links']['bot'], "url": "https://t.me/prankvzlomnewbot"},
                {"name": t['links']['tiktok'], "url": "https://www.tiktok.com/@jiarbuz"},
                {"name": t['links']['support'], "url": "https://t.me/PrankVzlomUnban"}
            ]
        },
        "software": [
            {"name": "SmartPSS", "url": "https://cloud.mail.ru/public/11we/vbzNxnSQi"},
            {"name": "Nesca", "url": "https://cloud.mail.ru/public/J2sJ/3vuy7XC1n"},
            {"name": "Noon", "url": "https://cloud.mail.ru/public/4Cmj/yMeVGQXE6"},
            {"name": "Ingram", "url": "https://cloud.mail.ru/public/nPCQ/JA73sB4tq"},
            {"name": "SoundPad", "url": "https://cloud.mail.ru/public/aFgC/FVg56TJqH"},
            {"name": "iVMS-4200", "url": "https://cloud.mail.ru/public/8t1M/g5zfvA8Lq"},
            {"name": "MVFPS", "url": "https://cloud.mail.ru/public/26ae/58VrzdvYT"},
            {"name": "KPortScan", "url": "https://cloud.mail.ru/public/yrup/9PQyDe86G"}
        ],
        "admins": {
            t['main_admin']: [
                {
                    "name": "Православный Бес", 
                    "url": "https://t.me/bes689",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-07-25_06-19-13.jpg"
                }
            ],
            t['creators']: [
                {
                    "name": "Everyday", 
                    "url": "https://t.me/mobile_everyday",
                    "avatar": "https://i.ibb.co/spKRJcmK/photo-2025-05-23-16-45-24.jpg"
                },
                {
                    "name": "Андрей", 
                    "url": "https://t.me/prankzvon231",
                    "avatar": None
                },
                {
                    "name": "Lucper", 
                    "url": "https://t.me/lucper1",
                    "avatar": "https://i.ibb.co/TMbSG0jp/photo-2025-07-20-01-44-45-2.gif"
                }
            ],
            t['senior_admins']: [
                {
                    "name": "Диванный воин Кчау", 
                    "url": "https://t.me/bestanov",
                    "avatar": "https://i.ibb.co/rKLcJ70c/photo-2025-04-23-02-37-37.jpg"
                },
                {
                    "name": "JIARBUZ.exe", 
                    "url": "https://t.me/jiarbuz",
                    "avatar": "https://i.ibb.co/kgBVDqM8/photo-2025-06-10-15-16-39.jpg"
                },
                {
                    "name": "ximi13p", 
                    "url": "https://t.me/ximi13p",
                    "avatar": None
                }
            ],
            t['junior_admins']: [
                {
                    "name": "k3stovski", 
                    "url": "https://t.me/k3stovski",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-07-24_23-01-05.jpg"
                },
                {
                    "name": "Жук", 
                    "url": "https://t.me/Sova_ingram",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-07-23_22-07-41.md.jpg"
                },
                {
                    "name": "Цыфра", 
                    "url": "https://t.me/himera_unturned",
                    "avatar": "https://i.ibb.co/LDCnnc2s/photo-2025-07-30-04-33-48-2.jpg"
                },
                {
                    "name": "Алексей Проктолог [ ПРОКТОЛОГИЯ ]", 
                    "url": "https://t.me/alexey_proktolog",
                    "avatar": "https://ltdfoto.ru/images/2025/07/29/photo_2025-07-24_02-53-41-3.jpg"
                },
                {
                    "name": "Наполеонский пистолэт", 
                    "url": "https://t.me/prnkzvn",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-07-20_04-28-28.jpg"
                },
                {
                    "name": "Kurapika",
                    "url": "https://t.me/kaiifaryk",
                    "avatar": "https://i.ibb.co/RkMpChw1/photo-2025-07-26-02-48-30.jpg"
                }
            ],
            t['senior_mods']: [
                {
                    "name": "Paul Du Rove", 
                    "url": "tg://openmessage?user_id=7401067755",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-05-03_16-27-45.jpg"
                },
                {
                    "name": "aiocryp", 
                    "url": "https://t.me/aiocryp",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-07-25_00-37-50.jpg"
                },
                {
                    "name": "саня шпалин", 
                    "url": "https://t.me/sanya_shpalka",
                    "avatar": "https://i.ibb.co/kVpDJYr6/photo-2025-07-29-04-56-12.jpg"
                },
                {
                    "name": "пряниковий манiяк", 
                    "url": "https://t.me/zxcarnagez2",
                    "avatar": "https://i.ibb.co/gbcg8v05/photo-2025-07-11-22-38-54.jpg"
                },
                {
                    "name": "ὙperBoreia", 
                    "url": "https://t.me/antikoks",
                    "avatar": "https://ltdfoto.ru/images/2025/07/29/photo_2025-07-27_18-51-08.jpg"
                },
            ]
        },
        "translations": t
    }
    return render_template('index.html', 
                         data=data,
                         bot_token=bot_token,
                         chat_id=chat_id,
                         current_lang=lang)

@app.route("/block_ip/<ip_to_block>", methods=["POST"])
def admin_block_ip(ip_to_block):
    # Тут должна быть проверка авторизации
    try:
        ipaddress.ip_address(ip_to_block)
    except ValueError:
        abort(400)
    blocked_ips[ip_to_block] = time.time() + BLOCK_DURATION
    save_blocked_ips()
    return f"IP {ip_to_block} заблокирован на {BLOCK_DURATION//3600} часов", 200

@app.errorhandler(403)
def forbidden(e):
    return "Доступ запрещён", 403

@app.errorhandler(429)
def too_many_requests(e):
    return "Слишком много запросов, попробуйте позже", 429

@app.errorhandler(500)
def internal_error(e):
    return "Внутренняя ошибка сервера", 500

@app.route('/home')
@limiter.limit("10 per minute")
def home():
    return redirect(url_for('index'))

@app.route('/change_language/<lang>')
def change_language(lang):
    if lang in ['ru', 'en']:
        session['lang'] = lang
    # Возвращаем на предыдущую страницу или на главную
    return redirect(request.referrer or url_for('index'))

@app.route('/sitemap.xml')
def sitemap():
    pages = []

    for rule in app.url_map.iter_rules():
        if "GET" in rule.methods and len(rule.arguments) == 0 and not rule.rule.startswith('/static'):
            url = url_for(rule.endpoint, _external=True)
            pages.append(url)

    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    for page in pages:
        sitemap_xml += '  <url>\n'
        sitemap_xml += f'    <loc>{page}</loc>\n'
        sitemap_xml += f'    <lastmod>{datetime.utcnow().date()}</lastmod>\n'
        sitemap_xml += '    <changefreq>weekly</changefreq>\n'
        sitemap_xml += '    <priority>0.8</priority>\n'
        sitemap_xml += '  </url>\n'

    sitemap_xml += '</urlset>'

    return Response(sitemap_xml, mimetype='application/xml')

@app.route('/set_language/<lang>')
@limiter.limit("5 per minute")
def set_language(lang):
    if lang in ['ru', 'en']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))

@app.before_request
def check_redis_on_start():
    if not hasattr(app, 'redis_initialized'):
        if redis_client:
            try:
                redis_client.ping()
                app.logger.info("Redis connection established")
            except Exception as e:
                app.logger.error(f"Redis connection failed: {str(e)}")
        app.redis_initialized = True

@app.route('/log', methods=['POST'])
def log():
    try:
        data = request.get_json()
        message = data.get('message')
        if not message:
            return jsonify({'error': 'No message provided'}), 400

        ip = get_client_ip()
        now = datetime.now()
        info = get_ip_info(ip)

        text = (
            f"📥 Лог\n"
            f"🕒 Время: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📡 IP: <code>{info.get('ip', ip)}</code>\n"
            f"🌍 Страна: {info.get('country', 'Unknown')}\n"
            f"🏙️ Город: {info.get('city', 'Unknown')}\n"
            f"🏢 Провайдер: {info.get('isp', 'Unknown')}\n"
            f"💬 Сообщение: {message}"
        )

        threading.Thread(target=send_telegram_message, args=(text,)).start()
        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        app.logger.error(f"Error in /log: {e}", exc_info=True)
        return jsonify({'error': 'Internal Server Error'}), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template('rate_limit.html'), 429

@app.after_request
def add_client_id_cookie(response):
    if not request.cookies.get("client_id"):
        client_id = str(uuid.uuid4())
        response.set_cookie(
            "client_id",
            client_id,
            max_age=86400 * 7,
            secure=True,
            httponly=True,
            samesite="Lax"
        )
    return response



# --- Запуск ---
if __name__ == "__main__":
    load_blocked_ips()
    app.run(host="0.0.0.0", port=5000, debug=(ENV!="production"))

<?php
// Безопасный логгер с лог-файлом, IP-фильтром и токеном
header('Content-Type: application/json');

// --- Настройки ---
$allowed_ips = ['127.0.0.1', '::1', '192.168.0.0/16']; // можно указать диапазоны
$log_file = __DIR__ . '/../logs/requests.log';

// --- Метод запроса ---
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    exit(json_encode(['error' => 'Method Not Allowed']));
}

// --- Загрузка .env ---
$env = parse_ini_file(__DIR__ . '/../.env');
$token = $env['TELEGRAM_BOT_TOKEN'] ?? '';
$chat_id = $env['TELEGRAM_CHAT_ID'] ?? '';
$access_token_env = $env['LOGGER_ACCESS_TOKEN'] ?? '';

if (!$token || !$chat_id || !$access_token_env) {
    http_response_code(500);
    exit(json_encode(['error' => 'Missing env credentials']));
}

// --- Проверка IP ---
function ip_in_range($ip, $range) {
    if (strpos($range, '/') === false) return $ip === $range;
    list($subnet, $bits) = explode('/', $range);
    $ip = ip2long($ip);
    $subnet = ip2long($subnet);
    $mask = -1 << (32 - $bits);
    return ($ip & $mask) === ($subnet & $mask);
}

$client_ip = $_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'];
$ip_allowed = false;
foreach ($allowed_ips as $range) {
    if (ip_in_range($client_ip, $range)) {
        $ip_allowed = true;
        break;
    }
}
if (!$ip_allowed) {
    http_response_code(403);
    exit(json_encode(['error' => 'IP not allowed']));
}

// --- Данные запроса ---
$data = json_decode(file_get_contents('php://input'), true);
if (!isset($data['access_token']) || $data['access_token'] !== $access_token_env) {
    http_response_code(401);
    exit(json_encode(['error' => 'Invalid token']));
}

$message = htmlspecialchars($data['message'] ?? 'No message', ENT_QUOTES, 'UTF-8');
$userAgent = $_SERVER['HTTP_USER_AGENT'] ?? 'Unknown';

// --- Геолокация ---
$geo = @file_get_contents("http://ip-api.com/json/{$client_ip}?fields=country,countryCode,query");
$geoInfo = json_decode($geo, true);
$country = $geoInfo['country'] ?? 'Unknown';
$countryCode = $geoInfo['countryCode'] ?? '--';

// --- Формирование лога ---
$log_text = "🛡️ <b>Лог с сайта:</b>\n"
          . "🌍 IP: <code>$client_ip</code>\n"
          . "📍 Страна: $country ($countryCode)\n"
          . "📱 User-Agent: $userAgent\n"
          . "💬 Сообщение: $message";

// --- Локальный лог-файл ---
$log_entry = "[" . date('Y-m-d H:i:s') . "] $client_ip - $message - $userAgent\n";
file_put_contents($log_file, $log_entry, FILE_APPEND);

// --- Telegram отправка ---
$response = @file_get_contents("https://api.telegram.org/bot{$token}/sendMessage?" . http_build_query([
    'chat_id' => $chat_id,
    'text' => $log_text,
    'parse_mode' => 'HTML'
]));

if ($response === false) {
    http_response_code(500);
    echo json_encode(['status' => 'fail']);
    exit;
}

http_response_code(200);
echo json_encode(['status' => 'ok']);

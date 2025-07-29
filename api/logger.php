<?php
header('Content-Type: application/json');

ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

// --- Настройки ---
$allowed_ips = ['127.0.0.1', '::1', '192.168.0.0/16']; // IP или диапазоны, с которых разрешён доступ
$log_file = __DIR__ . '/../logs/requests.log';

// --- Метод запроса ---
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Method Not Allowed']);
    exit;
}

// --- Загрузка .env ---
$env_path = __DIR__ . '/../.env';
if (!file_exists($env_path)) {
    http_response_code(500);
    echo json_encode(['error' => '.env not found']);
    exit;
}

$env = parse_ini_file($env_path);
$token = $env['TELEGRAM_BOT_TOKEN'] ?? '';
$chat_id = $env['TELEGRAM_CHAT_ID'] ?? '';
$access_token_env = $env['LOGGER_ACCESS_TOKEN'] ?? '';

if (!$token || !$chat_id || !$access_token_env) {
    http_response_code(500);
    echo json_encode(['error' => 'Missing env credentials']);
    exit;
}

// --- Проверка IP ---
function ip_in_range($ip, $range) {
    if (strpos($range, '/') === false) return $ip === $range;
    [$subnet, $bits] = explode('/', $range);
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
    echo json_encode(['error' => 'IP not allowed']);
    exit;
}

// --- Получаем данные запроса ---
$input = file_get_contents('php://input');
$data = json_decode($input, true);

if (!isset($data['access_token']) || $data['access_token'] !== $access_token_env) {
    http_response_code(401);
    echo json_encode(['error' => 'Invalid token']);
    exit;
}

$message = htmlspecialchars($data['message'] ?? 'No message', ENT_QUOTES, 'UTF-8');
$provider = htmlspecialchars($data['provider'] ?? 'Unknown', ENT_QUOTES, 'UTF-8');
$country = htmlspecialchars($data['country'] ?? 'Unknown (--)', ENT_QUOTES, 'UTF-8');
$city = htmlspecialchars($data['city'] ?? 'Unknown', ENT_QUOTES, 'UTF-8');
$userAgent = $_SERVER['HTTP_USER_AGENT'] ?? 'Unknown';

// --- Если в запросе нет страны, пытаемся определить через IP ---
if ($country === 'Unknown (--)' || $country === '') {
    $geo_json = @file_get_contents("http://ip-api.com/json/{$client_ip}?fields=country,countryCode,city");
    $geo = json_decode($geo_json, true);
    if ($geo && $geo['country']) {
        $country = htmlspecialchars($geo['country'] . " ({$geo['countryCode']})", ENT_QUOTES, 'UTF-8');
        $city = htmlspecialchars($geo['city'] ?? $city, ENT_QUOTES, 'UTF-8');
    }
}

// --- Формирование сообщения для Telegram ---
$log_text = "🛡️ <b>Лог с сайта</b>\n"
          . "🌍 IP: <code>{$client_ip}</code>\n"
          . "💻 Провайдер: {$provider}\n"
          . "📍 Страна: {$country}\n"
          . "🏙️ Город: {$city}\n"
          . "📱 UA: {$userAgent}\n"
          . "💬 Сообщение: {$message}";

// --- Запись в лог-файл ---
$log_entry = "[" . date('Y-m-d H:i:s') . "] $client_ip | $provider | $country | $city | $message | $userAgent\n";
file_put_contents($log_file, $log_entry, FILE_APPEND | LOCK_EX);

// --- Отправка в Telegram ---
$telegram_url = "https://api.telegram.org/bot{$token}/sendMessage";
$post_fields = [
    'chat_id' => $chat_id,
    'text' => $log_text,
    'parse_mode' => 'HTML',
];

// Инициализация cURL
$ch = curl_init();
curl_setopt($ch, CURLOPT_URL, $telegram_url);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, $post_fields);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);

// Отключаем проверку SSL (если проблема с сертификатом, в продакшене лучше не отключать)
curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 0);
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, 0);

$response = curl_exec($ch);

if (curl_errno($ch)) {
    $curl_error = curl_error($ch);
} else {
    $curl_error = null;
}

curl_close($ch);

$decoded = json_decode($response, true);

if (!$decoded || !isset($decoded['ok']) || !$decoded['ok']) {
    http_response_code(500);
    echo json_encode([
        'status' => 'fail',
        'telegram_error' => $decoded['description'] ?? 'Unknown error',
        'curl_error' => $curl_error,
        'raw_response' => $response,
    ]);
    exit;
}

// --- Успех ---
http_response_code(200);
echo json_encode(['status' => 'ok']);

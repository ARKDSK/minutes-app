<?php
declare(strict_types=1);

ini_set('display_errors', '0');
error_reporting(E_ALL);

session_set_cookie_params(['httponly' => true, 'samesite' => 'Lax']);
session_start();

$configFile = __DIR__ . '/../config/config.php';
if (!is_file($configFile)) {
    http_response_code(500);
    exit('config/config.php が見つかりません。config/config.example.php をコピーして設定してください。');
}
$config = require $configFile;

require_once __DIR__ . '/Db.php';
require_once __DIR__ . '/Auth.php';
require_once __DIR__ . '/Groq.php';
require_once __DIR__ . '/Pipeline.php';
require_once __DIR__ . '/View.php';

$db = new Db($config['db']);
$groq = new Groq(
    $config['groq_api_key'],
    $config['groq_chat_model'],
    $config['groq_whisper_model']
);
$pipeline = new Pipeline($groq);

<?php
// このファイルを config/config.php にコピーして値を設定してください。
// config/config.php はリポジトリに含めないでください。

return [
    'app_password' => 'change-me',

    'db' => [
        'host' => '127.0.0.1',
        'port' => 3306,
        'name' => 'minutes_app',
        'user' => 'minutes_user',
        'pass' => 'minutes_pass',
    ],

    'groq_api_key'      => '',
    'groq_chat_model'   => 'llama-3.1-8b-instant',
    'groq_whisper_model'=> 'whisper-large-v3-turbo',

    'upload_tmp_dir' => __DIR__ . '/../uploads',
    'max_upload_mb'  => 50,
];

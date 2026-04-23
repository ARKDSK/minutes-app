<?php
declare(strict_types=1);

/**
 * Groq API クライアント（curl 使用）
 *  - chat: テキストのみの応答
 *  - chatJson: JSON モードで構造化応答
 *  - transcribe: 音声ファイル → 文字起こし
 */
final class Groq
{
    private const CHAT_URL  = 'https://api.groq.com/openai/v1/chat/completions';
    private const AUDIO_URL = 'https://api.groq.com/openai/v1/audio/transcriptions';

    public function __construct(
        private string $apiKey,
        private string $chatModel,
        private string $whisperModel
    ) {}

    public function chat(string $prompt): string
    {
        $body = json_encode([
            'model'       => $this->chatModel,
            'messages'    => [['role' => 'user', 'content' => $prompt]],
            'temperature' => 0.2,
        ], JSON_UNESCAPED_UNICODE);

        $resp = $this->request(self::CHAT_URL, [
            'Authorization: Bearer ' . $this->apiKey,
            'Content-Type: application/json',
        ], $body);

        $data = json_decode($resp, true);
        return $data['choices'][0]['message']['content'] ?? '';
    }

    public function chatJson(string $prompt): array
    {
        $body = json_encode([
            'model'           => $this->chatModel,
            'messages'        => [['role' => 'user', 'content' => $prompt]],
            'response_format' => ['type' => 'json_object'],
            'temperature'     => 0.2,
        ], JSON_UNESCAPED_UNICODE);

        $resp = $this->request(self::CHAT_URL, [
            'Authorization: Bearer ' . $this->apiKey,
            'Content-Type: application/json',
        ], $body);

        $data = json_decode($resp, true);
        $content = $data['choices'][0]['message']['content'] ?? '{}';
        return json_decode($content, true) ?: [];
    }

    public function transcribe(string $filePath, string $filename): string
    {
        $mime = function_exists('mime_content_type')
            ? (mime_content_type($filePath) ?: 'application/octet-stream')
            : 'application/octet-stream';

        $fields = [
            'file'     => new CURLFile($filePath, $mime, $filename),
            'model'    => $this->whisperModel,
            'language' => 'ja',
        ];

        $resp = $this->request(self::AUDIO_URL, [
            'Authorization: Bearer ' . $this->apiKey,
        ], $fields);

        $data = json_decode($resp, true);
        return $data['text'] ?? '';
    }

    /** @param array|string $body */
    private function request(string $url, array $headers, $body): string
    {
        if ($this->apiKey === '') {
            throw new RuntimeException('GROQ_API_KEY が未設定です。');
        }
        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_POST           => true,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_HTTPHEADER     => $headers,
            CURLOPT_POSTFIELDS     => $body,
            CURLOPT_TIMEOUT        => 300,
        ]);
        $resp = curl_exec($ch);
        if ($resp === false) {
            $err = curl_error($ch);
            curl_close($ch);
            throw new RuntimeException("Groq HTTP error: $err");
        }
        $code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        if ($code >= 400) {
            throw new RuntimeException("Groq HTTP $code: " . substr((string)$resp, 0, 500));
        }
        return (string)$resp;
    }
}

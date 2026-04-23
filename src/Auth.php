<?php
declare(strict_types=1);

final class Auth
{
    public static function authed(): bool
    {
        return !empty($_SESSION['authed']);
    }

    public static function attemptLogin(string $password, string $expected): bool
    {
        if ($expected !== '' && hash_equals($expected, $password)) {
            $_SESSION['authed'] = true;
            session_regenerate_id(true);
            return true;
        }
        return false;
    }

    public static function logout(): void
    {
        $_SESSION = [];
        if (ini_get('session.use_cookies')) {
            $p = session_get_cookie_params();
            setcookie(session_name(), '', time() - 42000,
                $p['path'], $p['domain'], $p['secure'], $p['httponly']);
        }
        session_destroy();
    }

    public static function requireLogin(): void
    {
        if (!self::authed()) {
            header('Location: index.php?page=login');
            exit;
        }
    }

    public static function csrfToken(): string
    {
        if (empty($_SESSION['csrf'])) {
            $_SESSION['csrf'] = bin2hex(random_bytes(16));
        }
        return $_SESSION['csrf'];
    }

    public static function checkCsrf(): void
    {
        $tok = $_POST['csrf'] ?? '';
        if (!is_string($tok) || empty($_SESSION['csrf']) || !hash_equals($_SESSION['csrf'], $tok)) {
            http_response_code(400);
            exit('CSRF トークンが不正です。');
        }
    }
}

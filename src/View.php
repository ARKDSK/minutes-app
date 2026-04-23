<?php
declare(strict_types=1);

final class View
{
    public static function e(?string $s): string
    {
        return htmlspecialchars((string)$s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
    }

    public static function mmss(int|float|null $sec): string
    {
        $sec = (int)($sec ?? 0);
        return sprintf('%02d:%02d', intdiv($sec, 60), $sec % 60);
    }

    public static function render(string $view, array $data = [], ?string $activePage = null): void
    {
        extract($data, EXTR_SKIP);
        $activePage = $activePage ?? ($data['page'] ?? '');
        require __DIR__ . '/../views/_layout_header.php';
        require __DIR__ . '/../views/' . $view . '.php';
        require __DIR__ . '/../views/_layout_footer.php';
    }

    public static function renderBare(string $view, array $data = []): void
    {
        extract($data, EXTR_SKIP);
        require __DIR__ . '/../views/' . $view . '.php';
    }

    public static function allTags(array $rows): array
    {
        $seen = [];
        foreach ($rows as $r) {
            foreach (explode(',', $r['tags'] ?? '') as $t) {
                $t = trim($t);
                if ($t !== '') $seen[$t] = true;
            }
        }
        ksort($seen);
        return array_keys($seen);
    }
}

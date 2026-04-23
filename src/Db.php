<?php
declare(strict_types=1);

final class Db
{
    private PDO $pdo;

    public function __construct(array $cfg)
    {
        $dsn = sprintf(
            'mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4',
            $cfg['host'], (int)$cfg['port'], $cfg['name']
        );
        $this->pdo = new PDO($dsn, $cfg['user'], $cfg['pass'], [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES   => false,
        ]);
    }

    public function pdo(): PDO
    {
        return $this->pdo;
    }

    public function all(string $sql, array $params = []): array
    {
        $st = $this->pdo->prepare($sql);
        $st->execute($params);
        return $st->fetchAll();
    }

    public function one(string $sql, array $params = []): ?array
    {
        $st = $this->pdo->prepare($sql);
        $st->execute($params);
        $row = $st->fetch();
        return $row ?: null;
    }

    public function run(string $sql, array $params = []): int
    {
        $st = $this->pdo->prepare($sql);
        $st->execute($params);
        return $st->rowCount();
    }

    /** 議事録 JSON カラムをデコードして返す */
    public function hydrate(array $row): array
    {
        foreach (['analysis', 'summary_3', 'transcript_segments', 'bigrams'] as $col) {
            if (isset($row[$col]) && is_string($row[$col])) {
                $row[$col] = json_decode($row[$col], true) ?: [];
            }
        }
        return $row;
    }

    public function fetchMinutes(bool $light = false): array
    {
        $cols = $light
            ? 'id, date_str, title, participants, tags, analysis, summary_3'
            : 'id, date_str, title, participants, tags, content, analysis, summary_3, transcript_segments, bigrams';
        $rows = $this->all("SELECT $cols FROM minutes ORDER BY date_str DESC, created_at DESC");
        return array_map(fn($r) => $this->hydrate($r), $rows);
    }

    public function findMinute(string $id): ?array
    {
        $row = $this->one('SELECT * FROM minutes WHERE id = ?', [$id]);
        return $row ? $this->hydrate($row) : null;
    }
}

<?php
declare(strict_types=1);

/**
 * 議事録処理パイプライン
 *  - analyzeAndSummarize: 1 回の LLM 呼び出しで分析 + 3段階要約
 *  - autoTags: タグ自動生成
 *  - bigrams/cosine: 日本語向けの簡易文字 bigram ベクトルで類似度計算
 *  - searchMinutes: keyword + bigram cosine のハイブリッド検索
 *  - recommendSimilar: 類似会議レコメンド
 *  - answerCrossChat: 全議事録横断チャット
 */
final class Pipeline
{
    public function __construct(private Groq $groq) {}

    public function analyzeAndSummarize(string $text): array
    {
        $prompt = <<<PROMPT
以下の議事録を分析し、JSONのみで返してください。

項目:
- decisions: 決定事項の短い箇条書き（なければ空配列）
- pending: 保留事項の短い箇条書き（なければ空配列）
- todos: ToDoの短い箇条書き（なければ空配列）
- summary_level1: 1文で超要約
- summary_level2: 3〜5項目の要点
- summary_level3: 実行アクション中心の詳細要約（決定/保留/ToDoを含む）

議事録:
{$text}

出力フォーマット:
{"decisions":[],"pending":[],"todos":[],"summary_level1":"","summary_level2":[],"summary_level3":[]}
PROMPT;
        try {
            $data = $this->groq->chatJson($prompt);
        } catch (\Throwable $e) {
            return [
                ['decisions' => [], 'pending' => [], 'todos' => [], 'error' => $e->getMessage()],
                ['level1' => '', 'level2' => [], 'level3' => []],
            ];
        }
        $analysis = [
            'decisions' => $data['decisions'] ?? [],
            'pending'   => $data['pending']   ?? [],
            'todos'     => $data['todos']     ?? [],
        ];
        $summary = [
            'level1' => $data['summary_level1'] ?? '',
            'level2' => $data['summary_level2'] ?? [],
            'level3' => $data['summary_level3'] ?? [],
        ];
        return [$analysis, $summary];
    }

    public function autoTags(string $text, int $n = 5): string
    {
        $prompt = "次の議事録から、重要なキーワードを{$n}個だけ、カンマ区切りの1行で返してください。"
            . "固有名詞・技術用語・トピック名を優先し、一般語（会議・議事録・対応・内容など）は除外してください。\n\n"
            . "議事録:\n{$text}\n\n出力形式: キーワード1, キーワード2, ...";
        try {
            $line = trim($this->groq->chat($prompt));
            // LLM が改行を含めた場合の保険
            $line = explode("\n", $line)[0];
            return $line;
        } catch (\Throwable) {
            return '';
        }
    }

    /** 文字 bigram 頻度マップ */
    public function bigrams(string $text): array
    {
        $text = mb_strtolower($text, 'UTF-8');
        $text = (string)preg_replace('/\s+/u', ' ', $text);
        $chars = preg_split('//u', $text, -1, PREG_SPLIT_NO_EMPTY) ?: [];
        $bg = [];
        $len = count($chars);
        for ($i = 0; $i < $len - 1; $i++) {
            $pair = $chars[$i] . $chars[$i + 1];
            if (trim($pair) === '') continue;
            $bg[$pair] = ($bg[$pair] ?? 0) + 1;
        }
        return $bg;
    }

    public function cosine(array $a, array $b): float
    {
        if (!$a || !$b) return 0.0;
        $dot = 0.0;
        $na = 0.0;
        $nb = 0.0;
        foreach ($a as $v) $na += $v * $v;
        foreach ($b as $v) $nb += $v * $v;
        foreach ($a as $k => $v) {
            if (isset($b[$k])) $dot += $v * $b[$k];
        }
        $denom = sqrt($na) * sqrt($nb);
        return $denom > 0 ? $dot / $denom : 0.0;
    }

    public function keywordScore(string $query, array $row): int
    {
        $terms = preg_split('/\s+/u', trim($query)) ?: [];
        $hay = mb_strtolower(implode(' ', [
            $row['title']        ?? '',
            $row['content']      ?? '',
            $row['tags']         ?? '',
            implode(' ', (array)(($row['summary_3'] ?? [])['level2'] ?? [])),
        ]), 'UTF-8');
        $score = 0;
        foreach ($terms as $t) {
            if ($t === '') continue;
            $score += mb_substr_count($hay, mb_strtolower($t, 'UTF-8'));
        }
        return $score;
    }

    public function searchMinutes(
        string $query,
        array $rows,
        int $n = 5,
        ?string $dateFrom = null,
        ?string $dateTo = null,
        ?string $tag = null
    ): array {
        if ($dateFrom) $rows = array_values(array_filter($rows, fn($r) => ($r['date_str'] ?? '') >= $dateFrom));
        if ($dateTo)   $rows = array_values(array_filter($rows, fn($r) => ($r['date_str'] ?? '') <= $dateTo));
        if ($tag)      $rows = array_values(array_filter($rows, fn($r) => strpos($r['tags'] ?? '', $tag) !== false));
        if (!$rows)    return [];

        $qbg = $this->bigrams($query);
        $out = [];
        foreach ($rows as $r) {
            $bg  = $r['bigrams'] ?? [];
            $sem = $this->cosine($qbg, $bg);
            $key = $this->keywordScore($query, $r);
            $hybrid = $sem * 0.7 + min($key / 10.0, 1.0) * 0.3;
            $out[] = ['hybrid' => $hybrid, 'sem' => $sem, 'key' => $key, 'row' => $r];
        }
        usort($out, fn($a, $b) => $b['hybrid'] <=> $a['hybrid']);
        return array_slice($out, 0, $n);
    }

    public function recommendSimilar(array $target, array $rows, int $n = 3): array
    {
        if (empty($target['bigrams'])) return [];
        $out = [];
        foreach ($rows as $r) {
            if (($r['id'] ?? '') === ($target['id'] ?? '')) continue;
            if (empty($r['bigrams'])) continue;
            $out[] = ['sim' => $this->cosine($target['bigrams'], $r['bigrams']), 'row' => $r];
        }
        usort($out, fn($a, $b) => $b['sim'] <=> $a['sim']);
        return array_slice($out, 0, $n);
    }

    public function answerCrossChat(string $question, array $rows): array
    {
        $top = $this->searchMinutes($question, $rows, 5);
        $ctx = [];
        foreach ($top as $t) {
            $row = $t['row'];
            $a = $row['analysis'] ?? [];
            $ctx[] = sprintf(
                "- %s | %s | score=%.3f\n  決定事項: %s\n  保留事項: %s\n  ToDo: %s\n  本文抜粋: %s",
                $row['date_str'] ?? '', $row['title'] ?? '', $t['hybrid'],
                json_encode($a['decisions'] ?? [], JSON_UNESCAPED_UNICODE),
                json_encode($a['pending']   ?? [], JSON_UNESCAPED_UNICODE),
                json_encode($a['todos']     ?? [], JSON_UNESCAPED_UNICODE),
                mb_substr($row['content']   ?? '', 0, 400)
            );
        }
        $prompt = "以下の議事録コンテキストだけを根拠に回答してください。不明な点は不明と明示してください。\n\n"
            . "質問: {$question}\n\nコンテキスト:\n" . implode("\n\n", $ctx);
        try {
            $answer = $this->groq->chat($prompt);
        } catch (\Throwable $e) {
            $answer = 'LLM 呼び出しに失敗しました: ' . $e->getMessage();
        }
        return [$answer, $top];
    }
}

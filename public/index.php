<?php
declare(strict_types=1);

require_once __DIR__ . '/../src/bootstrap.php';

$page   = $_GET['page']   ?? 'list';
$action = $_POST['action'] ?? null;

try {
    // 認証なしで入れるのはログインページのみ
    if ($page === 'login') {
        if ($_SERVER['REQUEST_METHOD'] === 'POST') {
            Auth::checkCsrf();
            if (Auth::attemptLogin((string)($_POST['password'] ?? ''), (string)$config['app_password'])) {
                header('Location: index.php?page=list');
                exit;
            }
            $loginError = 'パスワードが違います';
        }
        View::render('login', ['loginError' => $loginError ?? null], 'login');
        exit;
    }

    if ($page === 'logout') {
        Auth::logout();
        header('Location: index.php?page=login');
        exit;
    }

    Auth::requireLogin();

    // --- POST アクション ---
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action !== null) {
        Auth::checkCsrf();

        switch ($action) {
            case 'save_minute': {
                $title        = trim((string)($_POST['title'] ?? ''));
                $date         = trim((string)($_POST['date'] ?? date('Y-m-d')));
                $participants = trim((string)($_POST['participants'] ?? ''));
                $tags         = trim((string)($_POST['tags'] ?? ''));
                $content      = trim((string)($_POST['content'] ?? ''));
                $segmentsJson = (string)($_POST['segments_json'] ?? '[]');
                $segments     = json_decode($segmentsJson, true) ?: [];

                if ($title === '' || $content === '') {
                    $flash = ['error' => 'タイトルと内容は必須です'];
                    break;
                }

                [$analysis, $summary3] = $pipeline->analyzeAndSummarize($content);
                $bigrams = $pipeline->bigrams($title . "\n" . $tags . "\n" . $content);

                $id = bin2hex(random_bytes(8)) . '-' . bin2hex(random_bytes(8));
                // UUID形式に整形
                $id = sprintf(
                    '%s-%s-%s-%s-%s',
                    substr($id, 0, 8), substr($id, 8, 4), substr($id, 12, 4),
                    substr($id, 16, 4), substr($id, 20, 12)
                );

                $db->run(
                    'INSERT INTO minutes
                     (id, date_str, title, participants, tags, content, analysis, summary_3, transcript_segments, bigrams)
                     VALUES (?,?,?,?,?,?,?,?,?,?)',
                    [
                        $id, $date, $title, $participants, $tags, $content,
                        json_encode($analysis, JSON_UNESCAPED_UNICODE),
                        json_encode($summary3, JSON_UNESCAPED_UNICODE),
                        json_encode($segments, JSON_UNESCAPED_UNICODE),
                        json_encode($bigrams,  JSON_UNESCAPED_UNICODE),
                    ]
                );
                $flash = ['success' => "「{$title}」を保存しました"];
                $page = 'list';
                break;
            }

            case 'delete_minute': {
                $id = (string)($_POST['id'] ?? '');
                if ($id !== '') {
                    $db->run('DELETE FROM minutes WHERE id = ?', [$id]);
                    $flash = ['success' => '削除しました'];
                }
                $page = 'list';
                break;
            }

            case 'transcribe': {
                if (empty($_FILES['audio']) || $_FILES['audio']['error'] !== UPLOAD_ERR_OK) {
                    $flash = ['error' => '音声ファイルのアップロードに失敗しました'];
                    $page = 'add';
                    break;
                }
                $maxBytes = (int)$config['max_upload_mb'] * 1024 * 1024;
                if ($_FILES['audio']['size'] > $maxBytes) {
                    $flash = ['error' => 'ファイルサイズが上限を超えています'];
                    $page = 'add';
                    break;
                }
                $tmp  = $_FILES['audio']['tmp_name'];
                $name = basename($_FILES['audio']['name']);
                try {
                    $text = $groq->transcribe($tmp, $name);
                    $_SESSION['draft'] = [
                        'content'       => $text,
                        'segments_json' => json_encode(
                            [['start' => 0, 'end' => 0, 'speaker' => '話者', 'text' => $text]],
                            JSON_UNESCAPED_UNICODE
                        ),
                    ];
                    $flash = ['success' => '文字起こしが完了しました。内容を確認して保存してください。'];
                } catch (\Throwable $e) {
                    $flash = ['error' => '文字起こし失敗: ' . $e->getMessage()];
                }
                $page = 'add';
                break;
            }

            case 'auto_tag': {
                $content = (string)($_POST['content'] ?? '');
                $tags = $content === '' ? '' : $pipeline->autoTags($content);
                $_SESSION['draft'] = array_merge($_SESSION['draft'] ?? [], [
                    'content' => $content,
                    'tags'    => $tags,
                ]);
                $page = 'add';
                break;
            }

            case 'cross_chat': {
                $question = trim((string)($_POST['question'] ?? ''));
                if ($question !== '') {
                    $rows = $db->fetchMinutes(false);
                    [$answer, $refs] = $pipeline->answerCrossChat($question, $rows);
                    $chatResult = ['question' => $question, 'answer' => $answer, 'refs' => $refs];
                }
                $page = 'chat';
                break;
            }
        }
    }

    // --- 画面描画 ---
    switch ($page) {
        case 'add':
            $draft = $_SESSION['draft'] ?? [];
            unset($_SESSION['draft']);
            View::render('add', ['flash' => $flash ?? null, 'draft' => $draft], 'add');
            break;

        case 'search':
            $rows       = $db->fetchMinutes(false);
            $q          = trim((string)($_GET['q'] ?? ''));
            $dateFrom   = (string)($_GET['date_from'] ?? '');
            $dateTo     = (string)($_GET['date_to']   ?? '');
            $tagFilter  = (string)($_GET['tag']       ?? '');
            $n          = max(1, min(20, (int)($_GET['n'] ?? 5)));
            $results    = $q === '' ? [] : $pipeline->searchMinutes(
                $q, $rows, $n,
                $dateFrom ?: null, $dateTo ?: null, $tagFilter ?: null
            );
            View::render('search', [
                'q' => $q, 'dateFrom' => $dateFrom, 'dateTo' => $dateTo,
                'tagFilter' => $tagFilter, 'n' => $n,
                'results' => $results, 'allTags' => View::allTags($rows),
            ], 'search');
            break;

        case 'detail':
            $id  = (string)($_GET['id'] ?? '');
            $row = $id ? $db->findMinute($id) : null;
            $similar = [];
            if ($row) {
                $all = $db->fetchMinutes(false);
                $similar = $pipeline->recommendSimilar($row, $all, 3);
            }
            View::render('detail', ['row' => $row, 'similar' => $similar], 'detail');
            break;

        case 'chat':
            View::render('chat', ['chatResult' => $chatResult ?? null, 'flash' => $flash ?? null], 'chat');
            break;

        case 'list':
        default:
            $rows = $db->fetchMinutes(true);
            View::render('list', ['rows' => $rows, 'flash' => $flash ?? null], 'list');
            break;
    }
} catch (\Throwable $e) {
    http_response_code(500);
    echo '<pre style="padding:16px;font-family:monospace">';
    echo 'エラー: ' . View::e($e->getMessage()) . "\n\n";
    echo View::e($e->getTraceAsString());
    echo '</pre>';
}

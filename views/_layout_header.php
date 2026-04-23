<?php /** @var ?string $activePage */ ?>
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>議事録検索システム</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<?php if (Auth::authed()): ?>
<header class="topbar">
  <h1>📋 議事録検索システム</h1>
  <nav>
    <?php
      $tabs = [
        'add'    => ['📝 議事録を追加', 'index.php?page=add'],
        'search' => ['🔍 検索',          'index.php?page=search'],
        'list'   => ['📄 一覧',          'index.php?page=list'],
        'detail' => ['📌 会議詳細',      'index.php?page=detail'],
        'chat'   => ['💬 AI横断チャット','index.php?page=chat'],
      ];
      foreach ($tabs as $key => [$label, $href]):
        $cls = ($activePage === $key) ? 'active' : '';
    ?>
      <a class="<?= $cls ?>" href="<?= $href ?>"><?= $label ?></a>
    <?php endforeach; ?>
    <a class="logout" href="index.php?page=logout">ログアウト</a>
  </nav>
</header>
<?php endif; ?>
<main class="container">

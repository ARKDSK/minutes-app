<?php
/** @var string $q @var string $dateFrom @var string $dateTo @var string $tagFilter */
/** @var int $n @var array $results @var array $allTags */
?>
<h2>🔍 検索（ハイブリッド: keyword + bigram 類似度）</h2>

<form method="get" action="index.php" class="card">
  <input type="hidden" name="page" value="search">
  <label>検索ワード
    <input type="text" name="q" value="<?= View::e($q) ?>" autofocus>
  </label>
  <div class="grid-3">
    <label>日付（開始）<input type="date" name="date_from" value="<?= View::e($dateFrom) ?>"></label>
    <label>日付（終了）<input type="date" name="date_to"   value="<?= View::e($dateTo) ?>"></label>
    <label>タグ
      <select name="tag">
        <option value="">（指定なし）</option>
        <?php foreach ($allTags as $t): ?>
          <option value="<?= View::e($t) ?>" <?= $tagFilter === $t ? 'selected' : '' ?>><?= View::e($t) ?></option>
        <?php endforeach; ?>
      </select>
    </label>
  </div>
  <label>表示件数
    <input type="number" name="n" min="1" max="20" value="<?= (int)$n ?>" style="width:80px">
  </label>
  <button type="submit" class="primary">検索</button>
</form>

<?php if ($q !== ''): ?>
  <?php if (!$results): ?>
    <p class="flash info">該当なし</p>
  <?php else: ?>
    <?php foreach ($results as $r): $row = $r['row']; ?>
      <details class="card">
        <summary>
          📅 <?= View::e($row['date_str']) ?> | <?= View::e($row['title']) ?>
          | hybrid=<?= number_format($r['hybrid'], 3) ?>
          (semantic=<?= number_format($r['sem'], 3) ?>, keyword=<?= (int)$r['key'] ?>)
        </summary>
        <p><strong>参加者:</strong> <?= View::e($row['participants'] ?: '-') ?></p>
        <p><strong>タグ:</strong> <?= View::e($row['tags'] ?: '-') ?></p>
        <?php include __DIR__ . '/_analysis.php'; ?>
        <?php include __DIR__ . '/_summary.php'; ?>
        <hr>
        <pre class="content"><?= View::e($row['content']) ?></pre>
        <p><a href="index.php?page=detail&id=<?= View::e($row['id']) ?>">→ 詳細を開く</a></p>
      </details>
    <?php endforeach; ?>
  <?php endif; ?>
<?php endif; ?>

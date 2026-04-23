<?php /** @var array $rows @var ?array $flash */ ?>
<h2>📄 議事録一覧</h2>

<?php if (!empty($flash['success'])): ?>
  <p class="flash success"><?= View::e($flash['success']) ?></p>
<?php endif; ?>
<?php if (!empty($flash['error'])): ?>
  <p class="flash error"><?= View::e($flash['error']) ?></p>
<?php endif; ?>

<p>登録件数: <strong><?= count($rows) ?>件</strong></p>

<?php if (!$rows): ?>
  <p>まだ議事録がありません。<a href="index.php?page=add">議事録を追加</a> から登録してください。</p>
<?php endif; ?>

<?php foreach ($rows as $row): ?>
  <details class="card">
    <summary>📅 <?= View::e($row['date_str']) ?> | <?= View::e($row['title']) ?></summary>
    <p><strong>参加者:</strong> <?= View::e($row['participants'] ?: '-') ?></p>
    <p><strong>タグ:</strong> <?= View::e($row['tags'] ?: '-') ?></p>
    <?php include __DIR__ . '/_analysis.php'; ?>
    <?php include __DIR__ . '/_summary.php'; ?>
    <p>
      <a href="index.php?page=detail&id=<?= View::e($row['id']) ?>">詳細</a>
      <form method="post" action="index.php?page=list" style="display:inline" onsubmit="return confirm('削除してよろしいですか？');">
        <input type="hidden" name="csrf" value="<?= View::e(Auth::csrfToken()) ?>">
        <input type="hidden" name="action" value="delete_minute">
        <input type="hidden" name="id" value="<?= View::e($row['id']) ?>">
        <button type="submit" class="danger-link">🗑️ 削除</button>
      </form>
    </p>
  </details>
<?php endforeach; ?>

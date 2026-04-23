<?php /** @var ?array $chatResult @var ?array $flash */ ?>
<h2>💬 AIチャット（全議事録横断質問）</h2>

<?php if (!empty($flash['error'])): ?>
  <p class="flash error"><?= View::e($flash['error']) ?></p>
<?php endif; ?>

<form method="post" action="index.php?page=chat" class="card">
  <input type="hidden" name="csrf" value="<?= View::e(Auth::csrfToken()) ?>">
  <input type="hidden" name="action" value="cross_chat">
  <label>質問
    <input type="text" name="question"
      value="<?= View::e($chatResult['question'] ?? '') ?>"
      placeholder="例: 認証基盤の決定事項と未解決課題を横断で教えて" required>
  </label>
  <button type="submit" class="primary">回答を生成</button>
</form>

<?php if (!empty($chatResult)): ?>
  <section class="card">
    <h3>回答</h3>
    <div class="answer"><?= nl2br(View::e($chatResult['answer'])) ?></div>
  </section>

  <section class="card">
    <h3>参照会議</h3>
    <?php if (!$chatResult['refs']): ?>
      <p>参照候補なし</p>
    <?php else: ?>
      <ul>
        <?php foreach ($chatResult['refs'] as $r): $row = $r['row']; ?>
          <li>
            <a href="index.php?page=detail&id=<?= View::e($row['id']) ?>"><?= View::e($row['date_str']) ?> | <?= View::e($row['title']) ?></a>
            （score=<?= number_format($r['hybrid'], 3) ?>）
          </li>
        <?php endforeach; ?>
      </ul>
    <?php endif; ?>
  </section>
<?php endif; ?>

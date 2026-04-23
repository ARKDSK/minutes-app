<?php /** @var ?array $row @var array $similar */ ?>
<h2>📌 会議詳細</h2>

<?php if (!$row): ?>
  <p class="flash info">会議を選択してください。</p>
  <p><a href="index.php?page=list">一覧へ戻る</a></p>
<?php else: ?>
  <section class="card">
    <h3><?= View::e($row['title']) ?></h3>
    <p class="muted">
      開催日: <?= View::e($row['date_str']) ?> /
      参加者: <?= View::e($row['participants'] ?: '-') ?> /
      タグ: <?= View::e($row['tags'] ?: '-') ?>
    </p>
    <?php include __DIR__ . '/_analysis.php'; ?>
    <?php include __DIR__ . '/_summary.php'; ?>
  </section>

  <section class="card">
    <h3>🎙️ タイムスタンプ付き文字起こし</h3>
    <?php $segs = $row['transcript_segments'] ?? []; ?>
    <?php if (!$segs): ?>
      <p>セグメントなし</p>
    <?php else: ?>
      <ul class="segments">
        <?php foreach ($segs as $s): $sec = (int)($s['start'] ?? 0); ?>
          <li>
            <span class="ts">[<?= View::mmss($sec) ?>]</span>
            <span class="sp"><?= View::e($s['speaker'] ?? '話者') ?>:</span>
            <?= View::e($s['text'] ?? '') ?>
          </li>
        <?php endforeach; ?>
      </ul>
    <?php endif; ?>
  </section>

  <section class="card">
    <h3>📚 類似会議レコメンド</h3>
    <?php if (!$similar): ?>
      <p>類似候補なし</p>
    <?php else: ?>
      <ul>
        <?php foreach ($similar as $s): $r = $s['row']; ?>
          <li>
            <a href="index.php?page=detail&id=<?= View::e($r['id']) ?>"><?= View::e($r['date_str']) ?> | <?= View::e($r['title']) ?></a>
            （類似度: <?= number_format($s['sim'], 2) ?>）
          </li>
        <?php endforeach; ?>
      </ul>
    <?php endif; ?>
  </section>

  <section class="card">
    <h3>本文</h3>
    <pre class="content"><?= View::e($row['content']) ?></pre>
  </section>
<?php endif; ?>

<?php
// 選択用の簡易セレクタ（全会議から切替）
$all = $db->fetchMinutes(true);
?>
<section class="card">
  <h3>別の会議を表示</h3>
  <form method="get" action="index.php">
    <input type="hidden" name="page" value="detail">
    <select name="id" onchange="this.form.submit()">
      <option value="">--選択--</option>
      <?php foreach ($all as $r): ?>
        <option value="<?= View::e($r['id']) ?>" <?= ($row && $row['id'] === $r['id']) ? 'selected' : '' ?>>
          <?= View::e($r['date_str']) ?> | <?= View::e($r['title']) ?>
        </option>
      <?php endforeach; ?>
    </select>
  </form>
</section>

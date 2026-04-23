<?php
/** @var array $row */
$s = $row['summary_3'] ?? [];
if (!$s) return;
?>
<p><strong>🧭 3段階要約</strong></p>
<?php if (!empty($s['level1'])): ?>
  <p class="callout"><?= View::e((string)$s['level1']) ?></p>
<?php endif; ?>
<?php if (!empty($s['level2'])): ?>
  <p><strong>要点</strong></p>
  <ul>
    <?php foreach ($s['level2'] as $x): ?>
      <li><?= View::e((string)$x) ?></li>
    <?php endforeach; ?>
  </ul>
<?php endif; ?>
<?php if (!empty($s['level3'])): ?>
  <p><strong>詳細要約（アクション中心）</strong></p>
  <ul>
    <?php foreach ($s['level3'] as $x): ?>
      <li><?= View::e((string)$x) ?></li>
    <?php endforeach; ?>
  </ul>
<?php endif; ?>

<?php
/** @var array $row */
$a = $row['analysis'] ?? [];
$sections = [
  ['✅ 決定事項', $a['decisions'] ?? []],
  ['⏸️ 保留事項', $a['pending']   ?? []],
  ['📌 ToDo',     $a['todos']     ?? []],
];
foreach ($sections as [$label, $items]):
  if (!$items) continue;
?>
  <p><strong><?= $label ?></strong></p>
  <ul>
    <?php foreach ($items as $x): ?>
      <li><?= View::e((string)$x) ?></li>
    <?php endforeach; ?>
  </ul>
<?php endforeach; ?>

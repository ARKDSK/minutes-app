<?php /** @var ?array $flash */ /** @var array $draft */ ?>
<h2>📝 議事録を追加</h2>

<?php if (!empty($flash['error'])): ?>
  <p class="flash error"><?= View::e($flash['error']) ?></p>
<?php elseif (!empty($flash['success'])): ?>
  <p class="flash success"><?= View::e($flash['success']) ?></p>
<?php endif; ?>

<section class="card">
  <h3>🎙️ 音声から文字起こし（任意）</h3>
  <form method="post" action="index.php?page=add" enctype="multipart/form-data">
    <input type="hidden" name="csrf" value="<?= View::e(Auth::csrfToken()) ?>">
    <input type="hidden" name="action" value="transcribe">
    <input type="file" name="audio" accept=".mp3,.wav,.m4a,.mp4,.ogg,.webm" required>
    <button type="submit">文字起こしする</button>
    <small>Groq Whisper API にアップロードします。</small>
  </form>
</section>

<section class="card">
  <h3>本文・メタ情報</h3>
  <form method="post" action="index.php?page=add">
    <input type="hidden" name="csrf" value="<?= View::e(Auth::csrfToken()) ?>">
    <input type="hidden" name="action" value="save_minute">
    <input type="hidden" name="segments_json" value='<?= View::e($draft['segments_json'] ?? "[]") ?>'>

    <div class="grid-2">
      <label>日付
        <input type="date" name="date" value="<?= View::e($draft['date'] ?? date('Y-m-d')) ?>" required>
      </label>
      <label>タイトル
        <input type="text" name="title" value="<?= View::e($draft['title'] ?? '') ?>" required placeholder="例：週次定例 4/20">
      </label>
    </div>
    <label>参加者（カンマ区切り）
      <input type="text" name="participants" value="<?= View::e($draft['participants'] ?? '') ?>">
    </label>
    <label>議事録内容
      <textarea name="content" rows="14" required placeholder="ここに議事録を貼り付けてください..."><?= View::e($draft['content'] ?? '') ?></textarea>
    </label>

    <div class="grid-2">
      <label>タグ（カンマ区切り）
        <input type="text" name="tags" value="<?= View::e($draft['tags'] ?? '') ?>">
      </label>
      <div class="inline-btn">
        <button type="submit" formaction="index.php?page=add" name="action" value="auto_tag">🏷️ タグ自動生成</button>
      </div>
    </div>

    <button type="submit" class="primary">💾 保存する</button>
  </form>
</section>

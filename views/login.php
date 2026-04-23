<?php /** @var ?string $loginError */ ?>
<section class="card" style="max-width:420px;margin:60px auto">
  <h2>🔒 ログイン</h2>
  <?php if (!empty($loginError)): ?>
    <p class="flash error"><?= View::e($loginError) ?></p>
  <?php endif; ?>
  <form method="post" action="index.php?page=login">
    <input type="hidden" name="csrf" value="<?= View::e(Auth::csrfToken()) ?>">
    <label>パスワード
      <input type="password" name="password" autofocus required>
    </label>
    <button type="submit" class="primary">ログイン</button>
  </form>
</section>

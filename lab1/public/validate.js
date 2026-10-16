// Cần nạp /rules.js trước file này (cung cấp hàm validateForm)
document.getElementById('f').addEventListener('submit', function (e) {
  const t0 = performance.now();
  const f = e.target;
  const errs = validateForm({
    username: f.username.value,
    email: f.email.value,
    password: f.password.value,
    confirm: f.confirm.value,
  });

  const ul = document.getElementById('errors');
  ul.innerHTML = '';
  if (errs.length) {
    e.preventDefault(); // chặn, KHÔNG gửi lên server
    errs.forEach(function (m) {
      const li = document.createElement('li');
      li.textContent = m;
      ul.appendChild(li);
    });
    console.log('Hiện lỗi sau ' + (performance.now() - t0).toFixed(2) + ' ms (local)');
  }
});

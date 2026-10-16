// Luật kiểm tra DÙNG CHUNG cho trình duyệt (validate.js), server (server.js) và measure.js
// -> client và server luôn kiểm tra giống hệt nhau.
function validateForm(v) {
  v = v || {};
  // ép kiểu chuỗi: tránh lỗi khi field thiếu hoặc bị gửi nhiều lần (thành mảng)
  const str = (x) => (typeof x === 'string' ? x : '');
  const username = str(v.username).trim();
  const email = str(v.email).trim();
  const password = str(v.password);
  const confirm = str(v.confirm);
  const errors = [];

  if (username.length < 4) errors.push('Username phải có ít nhất 4 ký tự.');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.push('Email không hợp lệ.');
  if (password.length < 8) errors.push('Mật khẩu phải có ít nhất 8 ký tự.');
  if (password !== confirm) errors.push('Mật khẩu nhập lại không khớp.');
  return errors;
}

if (typeof module !== 'undefined') module.exports = validateForm;

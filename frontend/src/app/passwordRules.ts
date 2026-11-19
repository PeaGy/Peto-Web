export const PASSWORD_MIN = 8;

/** Mật khẩu chỉ cần đủ dài (chủ web không muốn bắt có chữ, số hay ký tự đặc biệt); hai ô phải khớp. */
export function passwordProblem(password: string, again: string): string | null {
  if (password.length < PASSWORD_MIN) return `Mật khẩu cần ít nhất ${PASSWORD_MIN} ký tự.`;
  if (password !== again) return 'Hai mật khẩu chưa khớp.';
  return null;
}

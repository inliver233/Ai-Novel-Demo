export function shouldNotifyUnauthorized(status: number, errorCode?: string | null): boolean {
  if (status !== 401) return false;
  const code = String(errorCode ?? "")
    .trim()
    .toUpperCase();
  if (!code) return true;
  return code === "UNAUTHORIZED";
}

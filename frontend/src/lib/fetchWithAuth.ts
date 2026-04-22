/**
 * 인증 헤더를 자동으로 첨부하는 fetch 래퍼.
 * - localStorage의 access_token을 Authorization 헤더에 추가
 * - 401 응답 시 refresh_token으로 자동 재발급 후 재요청
 * - 재발급 실패 시 /auth/login으로 리다이렉트
 */

async function refreshTokens(): Promise<string | null> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return null;
  try {
    const res = await fetch("/api/v1/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    localStorage.setItem("user_id", data.user_id);
    localStorage.setItem("nickname", data.nickname ?? "");
    return data.access_token;
  } catch {
    return null;
  }
}

export async function fetchWithAuth(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = localStorage.getItem("access_token");

  const buildHeaders = (t: string | null): HeadersInit => ({
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
    ...(t ? { Authorization: `Bearer ${t}` } : {}),
  });

  let res = await fetch(url, { ...options, headers: buildHeaders(token) });

  if (res.status === 401) {
    const newToken = await refreshTokens();
    if (!newToken) {
      window.location.href = "/auth/login";
      throw new Error("인증이 만료되었습니다. 다시 로그인해주세요.");
    }
    res = await fetch(url, { ...options, headers: buildHeaders(newToken) });
  }

  return res;
}

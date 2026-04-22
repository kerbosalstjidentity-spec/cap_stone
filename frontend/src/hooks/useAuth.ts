"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

interface AuthState {
  userId: string;
  nickname: string;
  accessToken: string;
  isLoggedIn: boolean;
  isLoading: boolean;
}

/** JWT payload의 exp(만료시간)를 체크. 30초 여유 포함. */
function isTokenExpired(token: string): boolean {
  try {
    const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(base64));
    return payload.exp * 1000 < Date.now() + 30_000;
  } catch {
    return true;
  }
}

export function useAuth() {
  const router = useRouter();
  const [state, setState] = useState<AuthState>({
    userId: "",
    nickname: "",
    accessToken: "",
    isLoggedIn: false,
    isLoading: true,
  });

  /** 리프레시 토큰으로 액세스 토큰 갱신. 실패 시 null 반환. */
  const refresh = useCallback(async (): Promise<string | null> => {
    const refreshToken =
      typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null;
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
      setState({
        userId: data.user_id,
        nickname: data.nickname ?? "",
        accessToken: data.access_token,
        isLoggedIn: true,
        isLoading: false,
      });
      return data.access_token;
    } catch {
      return null;
    }
  }, []);

  /** 로그아웃: localStorage 초기화 후 로그인 페이지로 이동. */
  const logout = useCallback(() => {
    ["access_token", "refresh_token", "user_id", "nickname"].forEach((k) =>
      localStorage.removeItem(k)
    );
    setState({
      userId: "",
      nickname: "",
      accessToken: "",
      isLoggedIn: false,
      isLoading: false,
    });
    router.push("/auth/login");
  }, [router]);

  /** 초기 마운트 시 localStorage 확인 + 만료된 토큰 자동 갱신. */
  useEffect(() => {
    const init = async () => {
      if (typeof window === "undefined") return;
      const token = localStorage.getItem("access_token");
      const userId = localStorage.getItem("user_id") ?? "";
      const nickname = localStorage.getItem("nickname") ?? "";

      if (!token || !userId) {
        setState((s) => ({ ...s, isLoggedIn: false, isLoading: false }));
        return;
      }

      if (isTokenExpired(token)) {
        const newToken = await refresh();
        if (!newToken) {
          // 만료된 토큰 정리 — 로그인 페이지와의 리다이렉트 루프 방지
          ["access_token", "refresh_token", "user_id", "nickname"].forEach((k) =>
            localStorage.removeItem(k)
          );
          setState((s) => ({ ...s, isLoggedIn: false, isLoading: false }));
        }
        // refresh() 내부에서 setState 처리
        return;
      }

      setState({ userId, nickname, accessToken: token, isLoggedIn: true, isLoading: false });
    };
    init();
  }, [refresh]);

  return { ...state, logout, refresh };
}

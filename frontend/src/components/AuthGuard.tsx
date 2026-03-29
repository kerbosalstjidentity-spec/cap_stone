"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

/**
 * 인증이 필요한 페이지를 감싸는 가드 컴포넌트.
 * 로그인하지 않은 사용자는 /auth/login으로 자동 리다이렉트.
 */
export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isLoggedIn, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isLoggedIn) {
      router.replace("/auth/login");
    }
  }, [isLoggedIn, isLoading, router]);

  if (isLoading) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          height: "100vh",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <div style={{ fontSize: 32 }}>⏳</div>
        <p style={{ color: "var(--text-secondary)" }}>로딩 중...</p>
      </div>
    );
  }

  if (!isLoggedIn) return null;

  return <>{children}</>;
}

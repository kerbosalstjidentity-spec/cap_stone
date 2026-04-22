"use client";

import Link from "next/link";
import { useAuth } from "@/hooks/useAuth";
import NotificationBell from "./NotificationBell";

const NAV_LINKS = [
  { href: "/dashboard", label: "대시보드" },
  { href: "/analysis", label: "패턴 분석" },
  { href: "/strategy", label: "전략 제안" },
  { href: "/education", label: "교육" },
  { href: "/security", label: "보안" },
];

interface NavBarProps {
  activePath?: string;
}

export default function NavBar({ activePath }: NavBarProps) {
  const { isLoggedIn, isLoading, nickname, logout } = useAuth();

  return (
    <nav>
      <div
        className="container"
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
      >
        {/* 왼쪽: 로고 + 메뉴 */}
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <Link href="/" style={{ textDecoration: "none", marginRight: 12 }}>
            <h2 style={{ margin: 0, color: "var(--primary)" }}>ConsumePattern</h2>
          </Link>
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={activePath?.startsWith(link.href) ? "active" : ""}
            >
              {link.label}
            </Link>
          ))}
        </div>

        {/* 오른쪽: 사용자 정보 / 로그인 */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {!isLoading && isLoggedIn ? (
            <>
              <NotificationBell />
              <span style={{ fontSize: 14, color: "var(--text-secondary)" }}>
                👤 <strong>{nickname || "사용자"}</strong>
              </span>
              <button
                onClick={logout}
                style={{
                  padding: "5px 14px",
                  background: "transparent",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  cursor: "pointer",
                  fontSize: 13,
                  color: "var(--text-secondary)",
                }}
              >
                로그아웃
              </button>
            </>
          ) : !isLoading ? (
            <Link
              href="/auth/login"
              style={{ fontSize: 14, color: "var(--primary)", fontWeight: 600 }}
            >
              로그인
            </Link>
          ) : null}
        </div>
      </div>
    </nav>
  );
}

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // 이미 로그인된 경우 대시보드로 이동
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) router.replace("/dashboard");
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const data = await res.json();
        const detail = data.detail;
        const msg = Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join(" / ")
          : typeof detail === "string"
          ? detail
          : "로그인에 실패했습니다.";
        setError(msg);
        return;
      }
      const data = await res.json();
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("refresh_token", data.refresh_token);
      localStorage.setItem("user_id", data.user_id);
      localStorage.setItem("nickname", data.nickname);
      router.push("/dashboard");
    } catch {
      setError("서버에 연결할 수 없습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <nav>
        <div className="container">
          <h2><Link href="/" style={{ textDecoration: "none", color: "inherit" }}>ConsumePattern</Link></h2>
        </div>
      </nav>
      <main className="container" style={{ maxWidth: 440, paddingTop: 80 }}>
        <div className="card">
          <h2 style={{ marginBottom: 8 }}>로그인</h2>
          <p className="text-secondary" style={{ marginBottom: 24 }}>
            소비 패턴 분석 서비스에 오신 걸 환영합니다.
          </p>

          {error && (
            <div style={{
              background: "#fef2f2", border: "1px solid #fca5a5",
              borderRadius: 8, padding: "12px 16px", marginBottom: 16, color: "#dc2626",
            }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={{ display: "block", marginBottom: 6, fontWeight: 500 }}>이메일</label>
              <input
                type="email"
                value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                placeholder="your@email.com"
                required
                style={{
                  width: "100%", padding: "10px 14px", border: "1px solid #e5e7eb",
                  borderRadius: 8, fontSize: 14, boxSizing: "border-box",
                }}
              />
            </div>
            <div>
              <label style={{ display: "block", marginBottom: 6, fontWeight: 500 }}>비밀번호</label>
              <input
                type="password"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                placeholder="비밀번호 입력"
                required
                style={{
                  width: "100%", padding: "10px 14px", border: "1px solid #e5e7eb",
                  borderRadius: 8, fontSize: 14, boxSizing: "border-box",
                }}
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              style={{
                padding: "12px", background: "#6366f1", color: "#fff",
                border: "none", borderRadius: 8, fontWeight: 600, fontSize: 15,
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? "로그인 중..." : "로그인"}
            </button>
          </form>

          <p style={{ textAlign: "center", marginTop: 20, color: "#6b7280" }}>
            계정이 없으신가요?{" "}
            <Link href="/auth/register" style={{ color: "#6366f1", fontWeight: 500 }}>
              회원가입
            </Link>
          </p>
        </div>
      </main>
    </>
  );
}

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    email: "", password: "", nickname: "",
    age: "", occupation: "", monthly_income: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (form.password.length < 8) {
      setError("비밀번호는 8자 이상이어야 합니다.");
      return;
    }
    setLoading(true);
    try {
      const payload: Record<string, unknown> = {
        email: form.email,
        password: form.password,
        nickname: form.nickname,
      };
      if (form.age) payload.age = parseInt(form.age);
      if (form.occupation) payload.occupation = form.occupation;
      if (form.monthly_income) payload.monthly_income = parseFloat(form.monthly_income);

      const res = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || "회원가입에 실패했습니다.");
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

  const field = (label: string, key: keyof typeof form, type = "text", placeholder = "") => (
    <div>
      <label style={{ display: "block", marginBottom: 6, fontWeight: 500 }}>{label}</label>
      <input
        type={type}
        value={form[key]}
        onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
        placeholder={placeholder}
        style={{
          width: "100%", padding: "10px 14px", border: "1px solid #e5e7eb",
          borderRadius: 8, fontSize: 14, boxSizing: "border-box",
        }}
      />
    </div>
  );

  return (
    <>
      <nav>
        <div className="container">
          <h2>ConsumePattern</h2>
          <Link href="/">홈</Link>
        </div>
      </nav>
      <main className="container" style={{ maxWidth: 480, paddingTop: 60 }}>
        <div className="card">
          <h2 style={{ marginBottom: 8 }}>회원가입</h2>
          <p className="text-secondary" style={{ marginBottom: 24 }}>
            맞춤형 소비 분석을 시작해보세요.
          </p>

          {error && (
            <div style={{
              background: "#fef2f2", border: "1px solid #fca5a5",
              borderRadius: 8, padding: "12px 16px", marginBottom: 16, color: "#dc2626",
            }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {field("이메일 *", "email", "email", "your@email.com")}
            {field("비밀번호 * (8자 이상)", "password", "password", "비밀번호 입력")}
            {field("닉네임 *", "nickname", "text", "홍길동")}

            <div style={{ borderTop: "1px solid #f3f4f6", paddingTop: 14 }}>
              <p style={{ fontSize: 12, color: "#9ca3af", marginBottom: 10 }}>선택 정보 (더 정확한 분석에 활용됩니다)</p>
              <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                {field("나이", "age", "number", "25")}
                {field("직업", "occupation", "text", "직장인")}
              </div>
              <div style={{ marginTop: 12 }}>
                {field("월 수입 (원)", "monthly_income", "number", "3000000")}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                padding: "12px", background: "#6366f1", color: "#fff",
                border: "none", borderRadius: 8, fontWeight: 600, fontSize: 15,
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.7 : 1, marginTop: 4,
              }}
            >
              {loading ? "가입 중..." : "가입하기"}
            </button>
          </form>

          <p style={{ textAlign: "center", marginTop: 20, color: "#6b7280" }}>
            이미 계정이 있으신가요?{" "}
            <Link href="/auth/login" style={{ color: "#6366f1", fontWeight: 500 }}>
              로그인
            </Link>
          </p>
        </div>
      </main>
    </>
  );
}

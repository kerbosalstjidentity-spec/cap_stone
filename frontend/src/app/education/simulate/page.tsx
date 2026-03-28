"use client";

import { useState } from "react";
import Link from "next/link";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";

const CATEGORY_LABELS: Record<string, string> = {
  food: "식비", shopping: "쇼핑", transport: "교통", entertainment: "여가",
  education: "교육", healthcare: "의료", housing: "주거", utilities: "공과금",
  finance: "금융", travel: "여행", other: "기타",
};

function formatKRW(n: number): string {
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}만원`;
  return `${n.toLocaleString()}원`;
}

export default function SimulatePage() {
  const [userId, setUserId] = useState("demo_user");
  const [months, setMonths] = useState(12);
  const [reductions, setReductions] = useState<Record<string, number>>({});
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const setReduction = (cat: string, pct: number) => {
    setReductions({ ...reductions, [cat]: pct / 100 });
  };

  const simulate = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/v1/education/simulate/savings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, reduction_pct: reductions, months }),
      });
      const data = await res.json();
      if (res.ok) setResult(data);
      else setError(data.detail || "시뮬레이션에 실패했습니다.");
    } catch {
      setError("서버에 연결할 수 없습니다.");
    } finally {
      setLoading(false);
    }
  };

  const chartData = result ? Object.entries(result.before_after)
    .filter(([, v]: any) => v.before > 0)
    .sort(([, a]: any, [, b]: any) => b.before - a.before)
    .map(([cat, v]: any) => ({
      name: CATEGORY_LABELS[cat] || cat,
      "현재": Math.round(v.before),
      "절약 후": Math.round(v.after),
    })) : [];

  const categories = ["food", "shopping", "transport", "entertainment", "education",
    "healthcare", "housing", "utilities", "finance", "travel"];

  return (
    <>
      <nav>
        <div className="container">
          <h2>ConsumePattern</h2>
          <Link href="/dashboard">대시보드</Link>
          <Link href="/analysis">패턴 분석</Link>
          <Link href="/strategy">전략 제안</Link>
          <Link href="/education" className="active">교육</Link>
        </div>
      </nav>
      <main className="container">
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
          <h1>절약 시뮬레이션</h1>
        </div>

        <div className="grid grid-2">
          {/* 입력 패널 */}
          <div className="card">
            <h3 style={{ marginBottom: 16 }}>시뮬레이션 조건 설정</h3>
            <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
              <div>
                <label className="text-secondary" style={{ fontSize: 13, display: "block", marginBottom: 4 }}>사용자 ID</label>
                <input value={userId} onChange={(e) => setUserId(e.target.value)}
                  style={{ padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8, width: 150 }} />
              </div>
              <div>
                <label className="text-secondary" style={{ fontSize: 13, display: "block", marginBottom: 4 }}>시뮬레이션 기간</label>
                <select value={months} onChange={(e) => setMonths(Number(e.target.value))}
                  style={{ padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8 }}>
                  <option value={3}>3개월</option>
                  <option value={6}>6개월</option>
                  <option value={12}>1년</option>
                  <option value={24}>2년</option>
                  <option value={60}>5년</option>
                </select>
              </div>
            </div>

            <h4 style={{ marginBottom: 12 }}>카테고리별 절감 비율</h4>
            {categories.map((cat) => (
              <div key={cat} style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
                <span style={{ width: 60, fontSize: 14 }}>{CATEGORY_LABELS[cat]}</span>
                <input type="range" min={0} max={50} value={(reductions[cat] || 0) * 100}
                  onChange={(e) => setReduction(cat, Number(e.target.value))}
                  style={{ flex: 1 }} />
                <span style={{ width: 40, textAlign: "right", fontSize: 14, fontWeight: 600, color: "var(--primary)" }}>
                  {((reductions[cat] || 0) * 100).toFixed(0)}%
                </span>
              </div>
            ))}

            {/* 프리셋 버튼 */}
            <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
              <button onClick={() => setReductions({ food: 0.2, shopping: 0.3, entertainment: 0.3 })} style={{
                padding: "6px 14px", borderRadius: 8, border: "1px solid var(--border)",
                background: "#fff", cursor: "pointer", fontSize: 13,
              }}>
                기본 절약 플랜
              </button>
              <button onClick={() => setReductions({ food: 0.3, shopping: 0.5, entertainment: 0.5, travel: 0.5 })} style={{
                padding: "6px 14px", borderRadius: 8, border: "1px solid var(--border)",
                background: "#fff", cursor: "pointer", fontSize: 13,
              }}>
                강력 절약 플랜
              </button>
              <button onClick={() => setReductions({})} style={{
                padding: "6px 14px", borderRadius: 8, border: "1px solid var(--border)",
                background: "#fff", cursor: "pointer", fontSize: 13,
              }}>
                초기화
              </button>
            </div>

            <button onClick={simulate} disabled={loading} style={{
              width: "100%", marginTop: 20, padding: "12px", borderRadius: 8,
              border: "none", background: "var(--primary)", color: "#fff",
              fontSize: 15, cursor: "pointer",
            }}>
              {loading ? "계산 중..." : "시뮬레이션 실행"}
            </button>

            {error && <p style={{ color: "var(--danger)", marginTop: 8, fontSize: 14 }}>{error}</p>}
          </div>

          {/* 결과 패널 */}
          {result ? (
            <div className="card">
              <h3 style={{ marginBottom: 20 }}>시뮬레이션 결과</h3>

              {/* 핵심 수치 */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
                <div style={{ padding: 16, borderRadius: 10, background: "#f8fafc", textAlign: "center" }}>
                  <div className="stat-label">현재 월 지출</div>
                  <div style={{ fontSize: 24, fontWeight: 700 }}>{formatKRW(result.current_monthly)}</div>
                </div>
                <div style={{ padding: 16, borderRadius: 10, background: "#f0fdf4", textAlign: "center" }}>
                  <div className="stat-label">절약 후 월 지출</div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: "var(--success)" }}>{formatKRW(result.projected_monthly)}</div>
                </div>
                <div style={{ padding: 16, borderRadius: 10, background: "#fffbeb", textAlign: "center" }}>
                  <div className="stat-label">월 절약액</div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: "var(--warning)" }}>-{formatKRW(result.monthly_saving)}</div>
                </div>
                <div style={{ padding: 16, borderRadius: 10, background: "#eef2ff", textAlign: "center" }}>
                  <div className="stat-label">{result.months}개월 총 절약</div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: "var(--primary)" }}>{formatKRW(result.total_saving_over_period)}</div>
                </div>
              </div>

              {/* Before/After 차트 */}
              {chartData.length > 0 && (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={chartData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis type="number" tickFormatter={(v) => `${(v / 10000).toFixed(0)}만`} tick={{ fontSize: 12 }} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} width={50} />
                    <Tooltip formatter={(v: number) => formatKRW(v)} />
                    <Legend />
                    <Bar dataKey="현재" fill="#94a3b8" radius={[0, 4, 4, 0]} />
                    <Bar dataKey="절약 후" fill="#22c55e" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}

              {/* 카테고리별 절약 상세 */}
              <h4 style={{ marginTop: 20, marginBottom: 12 }}>카테고리별 월 절약액</h4>
              {Object.entries(result.category_savings)
                .filter(([, v]) => (v as number) > 0)
                .sort(([, a], [, b]) => (b as number) - (a as number))
                .map(([cat, saving]) => (
                  <div key={cat} style={{
                    display: "flex", justifyContent: "space-between", padding: "8px 0",
                    borderBottom: "1px solid var(--border)",
                  }}>
                    <span>{CATEGORY_LABELS[cat] || cat}</span>
                    <span style={{ fontWeight: 600, color: "var(--success)" }}>-{formatKRW(saving as number)}/월</span>
                  </div>
                ))}
            </div>
          ) : (
            <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
              <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>&#x1F4B0;</div>
              <p className="text-secondary" style={{ textAlign: "center" }}>
                카테고리별 절감 비율을 조정하고<br />시뮬레이션을 실행하세요
              </p>
            </div>
          )}
        </div>
      </main>
    </>
  );
}

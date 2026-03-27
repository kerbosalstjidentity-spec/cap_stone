"use client";

import { useState } from "react";
import Link from "next/link";

function formatKRW(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}만원`;
  return `${n.toLocaleString()}원`;
}

export default function StrategyPage() {
  const [userId, setUserId] = useState("demo_user");
  const [strategy, setStrategy] = useState<any>(null);
  const [compare, setCompare] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const fetchStrategy = async () => {
    setLoading(true);
    const [s, c] = await Promise.allSettled([
      fetch(`/api/v1/strategy/recommend/${userId}`).then((r) => r.json()),
      fetch(`/api/v1/analysis/compare/${userId}`).then((r) => r.json()),
    ]);
    if (s.status === "fulfilled") setStrategy(s.value);
    if (c.status === "fulfilled") setCompare(c.value);
    setLoading(false);
  };

  const riskColor = (score: number) =>
    score > 0.7 ? "var(--danger)" : score > 0.4 ? "var(--warning)" : "var(--success)";

  return (
    <>
      <nav>
        <div className="container">
          <h2>ConsumePattern</h2>
          <Link href="/dashboard">대시보드</Link>
          <Link href="/analysis">패턴 분석</Link>
          <Link href="/strategy" className="active">전략 제안</Link>
        </div>
      </nav>
      <main className="container">
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
          <h1>소비 전략 제안</h1>
          <input
            value={userId} onChange={(e) => setUserId(e.target.value)}
            style={{ padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8 }}
          />
          <button onClick={fetchStrategy} style={{
            padding: "8px 20px", background: "var(--primary)", color: "#fff",
            border: "none", borderRadius: 8, cursor: "pointer",
          }}>
            전략 조회
          </button>
        </div>

        {loading && <p>분석 중...</p>}

        <div className="grid grid-2">
          {/* 전략 추천 */}
          {strategy && (
            <div className="card">
              <h3>개인화 전략 추천</h3>
              <div style={{ margin: "16px 0", display: "flex", alignItems: "center", gap: 12 }}>
                <span className="badge badge-primary" style={{ fontSize: 16, padding: "6px 16px" }}>
                  {strategy.cluster_label}
                </span>
                <span style={{ color: riskColor(strategy.risk_score), fontWeight: 600 }}>
                  위험도 {(strategy.risk_score * 100).toFixed(0)}%
                </span>
              </div>
              {strategy.recommendations.map((rec: string, i: number) => (
                <div key={i} style={{
                  padding: "12px 16px", margin: "8px 0",
                  background: "#f8fafc", borderRadius: 8, borderLeft: "3px solid var(--primary)",
                }}>
                  {rec}
                </div>
              ))}
            </div>
          )}

          {/* 절약 기회 */}
          {strategy?.saving_opportunities?.length > 0 && (
            <div className="card">
              <h3>절약 가능 항목</h3>
              {strategy.saving_opportunities.map((s: any, i: number) => (
                <div key={i} style={{
                  padding: "12px 16px", margin: "8px 0",
                  background: "#f0fdf4", borderRadius: 8, borderLeft: "3px solid var(--success)",
                }}>
                  <div style={{ fontWeight: 600 }}>
                    {s.category} — {formatKRW(s.potential_saving)} 절약 가능
                  </div>
                  <div className="text-secondary">{s.reason}</div>
                </div>
              ))}
            </div>
          )}

          {/* 기간 비교 */}
          {compare && (
            <div className="card" style={{ gridColumn: "1 / -1" }}>
              <h3>전월 비교 분석</h3>
              <div style={{ margin: "16px 0", display: "flex", gap: 32 }}>
                <div>
                  <div className="stat-label">{compare.previous_period}</div>
                  <div className="stat-value" style={{ fontSize: 24 }}>
                    {formatKRW(compare.total_diff < 0
                      ? -compare.total_diff + (compare.total_diff + parseFloat(compare.total_diff))
                      : 0)}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center" }}>
                  <span style={{
                    fontSize: 24, fontWeight: 700,
                    color: compare.total_diff_pct > 0 ? "var(--danger)" : "var(--success)",
                  }}>
                    {compare.total_diff_pct > 0 ? "+" : ""}{compare.total_diff_pct.toFixed(1)}%
                  </span>
                </div>
              </div>
              <div style={{
                padding: 16, background: compare.total_diff_pct > 20 ? "#fef2f2" : "#f0fdf4",
                borderRadius: 8, fontSize: 15,
              }}>
                {compare.insight}
              </div>
            </div>
          )}
        </div>
      </main>
    </>
  );
}

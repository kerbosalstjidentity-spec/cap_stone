"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/hooks/useAuth";

const CATEGORY_LABELS: Record<string, string> = {
  food: "식비", shopping: "쇼핑", transport: "교통", entertainment: "여가",
  education: "교육", healthcare: "의료", housing: "주거", utilities: "공과금",
  finance: "금융", travel: "여행", other: "기타",
};

function formatKRW(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}만원`;
  return `${n.toLocaleString()}원`;
}

function DiffBadge({ pct }: { pct: number }) {
  const up = pct > 0;
  return (
    <span style={{ fontSize: 22, fontWeight: 700, color: up ? "var(--danger)" : "var(--success)" }}>
      {up ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

function StrategyContent() {
  const { userId } = useAuth();
  const [strategy, setStrategy] = useState<any>(null);
  const [compare, setCompare] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchStrategy = async () => {
    if (!userId) return;
    setLoading(true);
    setError("");
    const [s, c] = await Promise.allSettled([
      fetch(`/api/v1/strategy/recommend/${userId}`).then((r) => r.json()),
      fetch(`/api/v1/analysis/compare/${userId}`).then((r) => r.json()),
    ]);
    if (s.status === "fulfilled" && !s.value.detail) setStrategy(s.value);
    else if (s.status === "rejected" || s.value?.detail) setError("전략 데이터를 불러올 수 없습니다. 대시보드에서 먼저 데모 데이터를 생성하세요.");
    if (c.status === "fulfilled" && !c.value.detail) setCompare(c.value);
    setLoading(false);
  };

  useEffect(() => {
    if (userId) fetchStrategy();
  }, [userId]);

  const riskColor = (score: number) =>
    score > 0.7 ? "var(--danger)" : score > 0.4 ? "var(--warning)" : "var(--success)";

  return (
    <>
      <NavBar activePath="/strategy" />
      <main className="container">
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
          <h1>소비 전략 제안</h1>
          <button
            onClick={fetchStrategy}
            disabled={loading}
            style={{
              padding: "8px 20px", background: "var(--primary)", color: "#fff",
              border: "none", borderRadius: 8, cursor: "pointer", opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "분석 중..." : "새로고침"}
          </button>
        </div>

        {error && (
          <div className="card" style={{ color: "var(--danger)", marginBottom: 16 }}>{error}</div>
        )}

        <div className="grid grid-2">
          {strategy && (
            <div className="card">
              <h3>개인화 전략 추천</h3>
              <div style={{ margin: "16px 0", display: "flex", alignItems: "center", gap: 12 }}>
                <span className="badge badge-primary" style={{ fontSize: 15, padding: "6px 16px" }}>
                  {strategy.cluster_label}
                </span>
                <span style={{ color: riskColor(strategy.risk_score), fontWeight: 600 }}>
                  위험도 {(strategy.risk_score * 100).toFixed(0)}%
                </span>
                <div style={{ flex: 1, height: 8, background: "#e2e8f0", borderRadius: 4, overflow: "hidden" }}>
                  <div style={{
                    height: "100%", borderRadius: 4,
                    width: `${strategy.risk_score * 100}%`,
                    background: riskColor(strategy.risk_score),
                    transition: "width 0.5s ease",
                  }} />
                </div>
              </div>
              <div>
                {strategy.recommendations.map((rec: string, i: number) => (
                  <div key={i} style={{
                    padding: "12px 16px", margin: "8px 0",
                    background: "#f8fafc", borderRadius: 8,
                    borderLeft: "3px solid var(--primary)", fontSize: 14, lineHeight: 1.6,
                  }}>
                    {rec}
                  </div>
                ))}
              </div>
            </div>
          )}

          {strategy && (
            <div className="card">
              <h3>절약 가능 항목</h3>
              {strategy.saving_opportunities?.length > 0 ? (
                <>
                  <div style={{ margin: "12px 0 16px" }}>
                    <span className="text-secondary">총 절약 가능: </span>
                    <span style={{ fontSize: 22, fontWeight: 700, color: "var(--success)" }}>
                      {formatKRW(strategy.saving_opportunities.reduce((s: number, x: any) => s + x.potential_saving, 0))}
                    </span>
                  </div>
                  {strategy.saving_opportunities.map((s: any, i: number) => (
                    <div key={i} style={{ padding: "12px 16px", margin: "8px 0", background: "#f0fdf4", borderRadius: 8, borderLeft: "3px solid var(--success)" }}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>
                        {CATEGORY_LABELS[s.category] || s.category}
                        <span style={{ color: "var(--success)", marginLeft: 8 }}>-{formatKRW(s.potential_saving)}</span>
                      </div>
                      <div className="text-secondary" style={{ fontSize: 13 }}>{s.reason}</div>
                    </div>
                  ))}
                </>
              ) : (
                <div style={{ padding: 32, textAlign: "center" }}>
                  <div style={{ fontSize: 36 }}>🎉</div>
                  <p className="text-secondary" style={{ marginTop: 12 }}>현재 소비 패턴이 안정적입니다.</p>
                </div>
              )}
            </div>
          )}

          {compare && (
            <div className="card" style={{ gridColumn: "1 / -1" }}>
              <h3>전월 비교 분석</h3>
              <div style={{ margin: "20px 0", display: "flex", gap: 32, alignItems: "center", padding: "16px 24px", background: "#f8fafc", borderRadius: 10 }}>
                <div style={{ textAlign: "center" }}>
                  <div className="stat-label">{compare.previous_period}</div>
                  <div style={{ fontSize: 26, fontWeight: 700, color: "var(--text-secondary)" }}>{formatKRW(compare.previous_total)}</div>
                </div>
                <div style={{ fontSize: 28, color: "var(--text-secondary)" }}>→</div>
                <div style={{ textAlign: "center" }}>
                  <div className="stat-label">{compare.current_period}</div>
                  <div style={{ fontSize: 26, fontWeight: 700 }}>{formatKRW(compare.current_total)}</div>
                </div>
                <div style={{ flex: 1 }} />
                <div style={{ textAlign: "center" }}>
                  <DiffBadge pct={compare.total_diff_pct} />
                  <div className="text-secondary" style={{ fontSize: 13, marginTop: 4 }}>
                    {compare.total_diff > 0 ? "+" : ""}{formatKRW(compare.total_diff)}
                  </div>
                </div>
              </div>
              <h4 style={{ marginBottom: 12 }}>카테고리별 변화</h4>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
                {Object.entries(compare.category_diffs || {})
                  .sort(([, a], [, b]) => Math.abs(b as number) - Math.abs(a as number))
                  .map(([cat, diff]) => (
                    <div key={cat} style={{ padding: "10px 14px", borderRadius: 8, background: (diff as number) > 0 ? "#fef2f2" : "#f0fdf4", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 14 }}>{CATEGORY_LABELS[cat] || cat}</span>
                      <span style={{ fontWeight: 600, fontSize: 14, color: (diff as number) > 0 ? "var(--danger)" : "var(--success)" }}>
                        {(diff as number) > 0 ? "+" : ""}{formatKRW(diff as number)}
                      </span>
                    </div>
                  ))}
              </div>
              <div style={{
                marginTop: 16, padding: "14px 18px",
                background: compare.total_diff_pct > 20 ? "#fef2f2" : compare.total_diff_pct < -10 ? "#f0fdf4" : "#f8fafc",
                borderRadius: 8, fontSize: 15, lineHeight: 1.6,
                borderLeft: `4px solid ${compare.total_diff_pct > 20 ? "var(--danger)" : compare.total_diff_pct < -10 ? "var(--success)" : "var(--border)"}`,
              }}>
                💡 {compare.insight}
              </div>
            </div>
          )}

          {!strategy && !loading && (
            <div className="card" style={{ gridColumn: "1 / -1", textAlign: "center", padding: 48 }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>📊</div>
              <p className="text-secondary">소비 전략을 불러오는 중입니다...</p>
              <p className="text-secondary" style={{ fontSize: 13, marginTop: 8 }}>데이터가 없으면 대시보드에서 먼저 데모 데이터를 생성하세요.</p>
            </div>
          )}
        </div>
      </main>
    </>
  );
}

export default function StrategyPage() {
  return (
    <AuthGuard>
      <StrategyContent />
    </AuthGuard>
  );
}

"use client";

import { useState } from "react";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
} from "recharts";
import AuthGuard from "@/components/AuthGuard";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/hooks/useAuth";

const CATEGORY_LABELS: Record<string, string> = {
  food: "식비", shopping: "쇼핑", transport: "교통", entertainment: "여가",
  education: "교육", healthcare: "의료", housing: "주거", utilities: "공과금",
  finance: "금융", travel: "여행", other: "기타",
};

const CATEGORY_COLORS: Record<string, string> = {
  food: "#ef4444", shopping: "#f59e0b", transport: "#3b82f6",
  entertainment: "#8b5cf6", education: "#22c55e", healthcare: "#06b6d4",
  housing: "#ec4899", utilities: "#64748b", finance: "#14b8a6",
  travel: "#f97316", other: "#94a3b8",
};

function formatKRW(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}만원`;
  return `${n.toLocaleString()}원`;
}

function AnalysisContent() {
  const { userId } = useAuth();
  const [pattern, setPattern] = useState<any>(null);
  const [anomalies, setAnomalies] = useState<any>(null);
  const [forecast, setForecast] = useState<any>(null);
  const [overspend, setOverspend] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const runAnalysis = async () => {
    if (!userId) return;
    setLoading(true);
    setError("");
    try {
      const [p, a, f, o] = await Promise.allSettled([
        fetch(`/api/v1/analysis/pattern/${userId}`).then((r) => {
          if (!r.ok) throw new Error(`pattern ${r.status}`);
          return r.json();
        }),
        fetch(`/api/v1/analysis/anomaly/${userId}`).then((r) => {
          if (!r.ok) throw new Error(`anomaly ${r.status}`);
          return r.json();
        }),
        fetch(`/api/v1/analysis/forecast/${userId}`).then((r) => {
          if (!r.ok) throw new Error(`forecast ${r.status}`);
          return r.json();
        }),
        fetch(`/api/v1/analysis/overspend/${userId}`).then((r) => {
          if (!r.ok) throw new Error(`overspend ${r.status}`);
          return r.json();
        }),
      ]);
      if (p.status === "fulfilled" && !p.value?.detail) setPattern(p.value);
      if (a.status === "fulfilled" && !a.value?.detail) setAnomalies(a.value);
      if (f.status === "fulfilled" && !f.value?.detail) setForecast(f.value);
      if (o.status === "fulfilled" && !o.value?.detail) setOverspend(o.value);

      const allFailed = [p, a, f, o].every((r) => r.status === "rejected");
      if (allFailed) setError("분석 데이터를 불러올 수 없습니다. 대시보드에서 먼저 데모 데이터를 생성해주세요.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const clusterBadge = (label: string) => {
    const map: Record<string, string> = {
      "절약형": "badge-success", "균형형": "badge-primary",
      "소비형": "badge-warning", "과소비형": "badge-danger",
    };
    return map[label] || "badge-primary";
  };

  const radarData = pattern?.category_breakdown?.map((cat: any) => ({
    category: CATEGORY_LABELS[cat.category] || cat.category,
    pct: Math.round(cat.pct_of_total * 100),
  })) || [];

  const forecastBarData = forecast?.predicted_by_category
    ? Object.entries(forecast.predicted_by_category).map(([cat, amt]) => ({
        name: CATEGORY_LABELS[cat] || cat,
        amount: amt as number,
        color: CATEGORY_COLORS[cat] || "#94a3b8",
      }))
    : [];

  return (
    <>
      <NavBar activePath="/analysis" />
      <main className="container">
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
          <h1>소비 패턴 분석</h1>
          <button
            onClick={runAnalysis}
            disabled={loading}
            style={{
              padding: "8px 20px", background: "var(--primary)", color: "#fff",
              border: "none", borderRadius: 8, cursor: "pointer", opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "분석 중..." : "분석 실행"}
          </button>
        </div>

        {error && (
          <div className="card" style={{ color: "var(--danger)", marginBottom: 16, display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 20 }}>⚠️</span>
            <span>{error}</span>
          </div>
        )}

        <div className="grid grid-2">
          {pattern && (
            <div className="card">
              <h3>소비 유형 (K-Means 군집화)</h3>
              <div style={{ margin: "16px 0", display: "flex", alignItems: "center", gap: 12 }}>
                <span className={`badge ${clusterBadge(pattern.cluster_label)}`} style={{ fontSize: 18, padding: "8px 20px" }}>
                  {pattern.cluster_label}
                </span>
                <span className="text-secondary">{pattern.tx_count}건 · 평균 {formatKRW(pattern.avg_amount)}/건</span>
              </div>
              {radarData.length > 0 && (
                <ResponsiveContainer width="100%" height={260}>
                  <RadarChart data={radarData} outerRadius={85}>
                    <PolarGrid stroke="#e2e8f0" />
                    <PolarAngleAxis dataKey="category" tick={{ fontSize: 12, fill: "#64748b" }} />
                    <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 9 }} tickCount={4} />
                    <Radar dataKey="pct" stroke="#4f46e5" fill="#4f46e5" fillOpacity={0.35} dot={{ r: 3, fill: "#4f46e5" }} />
                    <Tooltip formatter={(v: number) => `${v}%`} />
                  </RadarChart>
                </ResponsiveContainer>
              )}
            </div>
          )}

          {anomalies && (
            <div className="card">
              <h3>이상 지출 탐지 (Isolation Forest)</h3>
              <div style={{ margin: "16px 0", display: "flex", alignItems: "center", gap: 12 }}>
                <span className={`badge ${anomalies.anomaly_count > 0 ? "badge-danger" : "badge-success"}`} style={{ fontSize: 16, padding: "6px 16px" }}>
                  {anomalies.anomaly_count > 0 ? `${anomalies.anomaly_count}건 감지` : "이상 없음"}
                </span>
                <span className="text-secondary">전체 {anomalies.total_transactions}건 중 분석</span>
              </div>
              <div style={{ maxHeight: 300, overflowY: "auto" }}>
                {anomalies.anomalies?.length > 0 ? (
                  anomalies.anomalies.map((a: any, i: number) => (
                    <div key={i} style={{ marginTop: 8, padding: "10px 12px", background: "#fef2f2", borderRadius: 8, borderLeft: "3px solid var(--danger)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ fontWeight: 600, color: "var(--danger)" }}>{formatKRW(a.amount)}</span>
                        <span className="badge badge-danger" style={{ fontSize: 11 }}>score: {a.anomaly_score.toFixed(3)}</span>
                      </div>
                      <div className="text-secondary" style={{ fontSize: 13, marginTop: 4 }}>{a.reason}</div>
                    </div>
                  ))
                ) : (
                  <div style={{ padding: 24, textAlign: "center" }}>
                    <span style={{ fontSize: 32 }}>✅</span>
                    <p className="text-secondary" style={{ marginTop: 8 }}>모든 거래가 정상 범위입니다</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {forecast && (
            <div className="card">
              <h3>다음 달 지출 예측 (LSTM)</h3>
              <div style={{ margin: "16px 0" }}>
                <div className="stat-value">{formatKRW(forecast.predicted_total)}</div>
                <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
                  <span className="badge badge-primary">신뢰도 {(forecast.confidence * 100).toFixed(0)}%</span>
                  <span className="badge" style={{ background: "#f8fafc", color: "var(--text-secondary)" }}>
                    방법: {forecast.confidence > 0.6 ? "LSTM" : "가중이동평균"}
                  </span>
                </div>
              </div>
              {forecastBarData.length > 0 && (
                <ResponsiveContainer width="100%" height={Math.max(160, forecastBarData.length * 26)}>
                  <BarChart data={[...forecastBarData].sort((a, b) => (b.amount as number) - (a.amount as number))} layout="vertical" margin={{ left: 4, right: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                    <XAxis type="number" tickFormatter={(v) => `${(v / 10000).toFixed(0)}만`} tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} width={42} />
                    <Tooltip formatter={(v: number) => [formatKRW(v), "예측 금액"]} />
                    <Bar dataKey="amount" radius={[0, 5, 5, 0]} maxBarSize={18}>
                      {forecastBarData.map((entry, idx) => <Cell key={idx} fill={entry.color} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          )}

          {overspend && (
            <div className="card">
              <h3>과소비 위험도 (XGBoost)</h3>
              <div style={{ margin: "16px 0", textAlign: "center" }}>
                {(() => {
                  const pct = overspend.overspend_probability;
                  const r = 60;
                  const arcLen = Math.PI * r;
                  const gaugeColor = pct > 0.6 ? "var(--danger)" : pct > 0.35 ? "#f59e0b" : "var(--success)";
                  return (
                    <svg width="160" height="95" viewBox="0 0 160 90" style={{ overflow: "visible", margin: "0 auto", display: "block" }}>
                      <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" stroke="#e2e8f0" strokeWidth="14" strokeLinecap="round" />
                      <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" stroke={gaugeColor} strokeWidth="14" strokeLinecap="round"
                        strokeDasharray={arcLen} strokeDashoffset={arcLen * (1 - pct)} />
                      <text x="80" y="72" textAnchor="middle" fontSize="22" fontWeight="700" fill={gaugeColor}>
                        {(pct * 100).toFixed(1)}%
                      </text>
                    </svg>
                  );
                })()}
                <span className={`badge ${overspend.is_overspend ? "badge-danger" : "badge-success"}`} style={{ marginTop: 4, display: "inline-block" }}>
                  {overspend.is_overspend ? "과소비 주의" : "정상 범위"}
                </span>
              </div>
              <div style={{ marginTop: 16, display: "flex", justifyContent: "space-between" }}>
                <div><div className="stat-label">이번 달</div><div style={{ fontWeight: 600 }}>{formatKRW(overspend.monthly_total)}</div></div>
                <div><div className="stat-label">월 평균</div><div style={{ fontWeight: 600 }}>{formatKRW(overspend.monthly_avg)}</div></div>
                <div><div className="stat-label">분석 방법</div><div style={{ fontWeight: 600 }}>{overspend.method}</div></div>
              </div>
            </div>
          )}

          {!pattern && !anomalies && !forecast && !overspend && !loading && !error && (
            <div className="card" style={{ gridColumn: "1 / -1", textAlign: "center", padding: 48 }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>🔬</div>
              <p className="text-secondary">분석 실행 버튼을 눌러 내 소비 패턴을 분석하세요.</p>
              <p className="text-secondary" style={{ fontSize: 13, marginTop: 8 }}>대시보드에서 먼저 데모 데이터를 생성해야 합니다.</p>
            </div>
          )}
        </div>
      </main>
    </>
  );
}

export default function AnalysisPage() {
  return (
    <AuthGuard>
      <AnalysisContent />
    </AuthGuard>
  );
}

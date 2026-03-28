"use client";

import { useState } from "react";
import Link from "next/link";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
} from "recharts";

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

export default function AnalysisPage() {
  const [userId, setUserId] = useState("demo_user");
  const [pattern, setPattern] = useState<any>(null);
  const [anomalies, setAnomalies] = useState<any>(null);
  const [forecast, setForecast] = useState<any>(null);
  const [overspend, setOverspend] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const runAnalysis = async () => {
    setLoading(true);
    const [p, a, f, o] = await Promise.allSettled([
      fetch(`/api/v1/analysis/pattern/${userId}`).then((r) => r.json()),
      fetch(`/api/v1/analysis/anomaly/${userId}`).then((r) => r.json()),
      fetch(`/api/v1/analysis/forecast/${userId}`).then((r) => r.json()),
      fetch(`/api/v1/analysis/overspend/${userId}`).then((r) => r.json()),
    ]);
    if (p.status === "fulfilled") setPattern(p.value);
    if (a.status === "fulfilled") setAnomalies(a.value);
    if (f.status === "fulfilled") setForecast(f.value);
    if (o.status === "fulfilled") setOverspend(o.value);
    setLoading(false);
  };

  const clusterBadge = (label: string) => {
    const map: Record<string, string> = {
      "절약형": "badge-success", "균형형": "badge-primary",
      "소비형": "badge-warning", "과소비형": "badge-danger",
    };
    return map[label] || "badge-primary";
  };

  // K-Means 레이더 차트 데이터
  const radarData = pattern?.category_breakdown?.map((cat: any) => ({
    category: CATEGORY_LABELS[cat.category] || cat.category,
    pct: Math.round(cat.pct_of_total * 100),
  })) || [];

  // 예측 카테고리별 바 차트 데이터
  const forecastBarData = forecast?.predicted_by_category
    ? Object.entries(forecast.predicted_by_category).map(([cat, amt]) => ({
        name: CATEGORY_LABELS[cat] || cat,
        amount: amt as number,
        color: CATEGORY_COLORS[cat] || "#94a3b8",
      }))
    : [];

  return (
    <>
      <nav>
        <div className="container">
          <h2>ConsumePattern</h2>
          <Link href="/dashboard">대시보드</Link>
          <Link href="/analysis" className="active">패턴 분석</Link>
          <Link href="/strategy">전략 제안</Link>
          <Link href="/education">교육</Link>
        </div>
      </nav>
      <main className="container">
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
          <h1>소비 패턴 분석</h1>
          <input
            value={userId} onChange={(e) => setUserId(e.target.value)}
            style={{ padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8 }}
          />
          <button onClick={runAnalysis} style={{
            padding: "8px 20px", background: "var(--primary)", color: "#fff",
            border: "none", borderRadius: 8, cursor: "pointer",
          }}>
            분석 실행
          </button>
        </div>

        {loading && <p>분석 중...</p>}

        <div className="grid grid-2">
          {/* K-Means 군집 분석 + 레이더 차트 */}
          {pattern && (
            <div className="card">
              <h3>소비 유형 (K-Means 군집화)</h3>
              <div style={{ margin: "16px 0", display: "flex", alignItems: "center", gap: 12 }}>
                <span className={`badge ${clusterBadge(pattern.cluster_label)}`} style={{ fontSize: 18, padding: "8px 20px" }}>
                  {pattern.cluster_label}
                </span>
                <span className="text-secondary">
                  {pattern.tx_count}건 · 평균 {formatKRW(pattern.avg_amount)}/건
                </span>
              </div>
              {radarData.length > 0 && (
                <ResponsiveContainer width="100%" height={260}>
                  <RadarChart data={radarData} outerRadius={85}>
                    <PolarGrid stroke="#e2e8f0" />
                    <PolarAngleAxis dataKey="category" tick={{ fontSize: 12, fill: "#64748b" }} />
                    <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 9 }} tickCount={4} />
                    <Radar dataKey="pct" stroke="#4f46e5" fill="#4f46e5" fillOpacity={0.35}
                      dot={{ r: 3, fill: "#4f46e5" }} />
                    <Tooltip formatter={(v: number) => `${v}%`} />
                  </RadarChart>
                </ResponsiveContainer>
              )}
            </div>
          )}

          {/* Isolation Forest 이상 탐지 */}
          {anomalies && (
            <div className="card">
              <h3>이상 지출 탐지 (Isolation Forest)</h3>
              <div style={{ margin: "16px 0", display: "flex", alignItems: "center", gap: 12 }}>
                <span className={`badge ${anomalies.anomaly_count > 0 ? "badge-danger" : "badge-success"}`}
                  style={{ fontSize: 16, padding: "6px 16px" }}>
                  {anomalies.anomaly_count > 0 ? `${anomalies.anomaly_count}건 감지` : "이상 없음"}
                </span>
                <span className="text-secondary">
                  전체 {anomalies.total_transactions}건 중 분석
                </span>
              </div>
              <div style={{ maxHeight: 300, overflowY: "auto" }}>
                {anomalies.anomalies?.length > 0 ? (
                  anomalies.anomalies.map((a: any, i: number) => (
                    <div key={i} style={{
                      marginTop: 8, padding: "10px 12px", background: "#fef2f2",
                      borderRadius: 8, borderLeft: "3px solid var(--danger)",
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ fontWeight: 600, color: "var(--danger)" }}>{formatKRW(a.amount)}</span>
                        <span className="badge badge-danger" style={{ fontSize: 11 }}>
                          score: {a.anomaly_score.toFixed(3)}
                        </span>
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

          {/* LSTM 예측 + 바 차트 */}
          {forecast && (
            <div className="card">
              <h3>다음 달 지출 예측 (LSTM)</h3>
              <div style={{ margin: "16px 0" }}>
                <div className="stat-value">{formatKRW(forecast.predicted_total)}</div>
                <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
                  <span className="badge badge-primary">
                    신뢰도 {(forecast.confidence * 100).toFixed(0)}%
                  </span>
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
                      {forecastBarData.map((entry, idx) => (
                        <Cell key={idx} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          )}

          {/* XGBoost 과소비 확률 */}
          {overspend && (
            <div className="card">
              <h3>과소비 위험도 (XGBoost)</h3>
              <div style={{ margin: "16px 0", textAlign: "center" }}>
                {/* SVG 반원 게이지 */}
                {(() => {
                  const pct = overspend.overspend_probability;
                  const r = 60;
                  const arcLen = Math.PI * r;
                  const gaugeColor = pct > 0.6 ? "var(--danger)" : pct > 0.35 ? "#f59e0b" : "var(--success)";
                  return (
                    <svg width="160" height="95" viewBox="0 0 160 90" style={{ overflow: "visible", margin: "0 auto", display: "block" }}>
                      {/* 배경 호 */}
                      <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" stroke="#e2e8f0" strokeWidth="14" strokeLinecap="round" />
                      {/* 값 호 */}
                      <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none"
                        stroke={gaugeColor} strokeWidth="14" strokeLinecap="round"
                        strokeDasharray={arcLen}
                        strokeDashoffset={arcLen * (1 - pct)}
                      />
                      {/* 퍼센트 텍스트 */}
                      <text x="80" y="72" textAnchor="middle" fontSize="22" fontWeight="700" fill={gaugeColor}>
                        {(pct * 100).toFixed(1)}%
                      </text>
                    </svg>
                  );
                })()}
                <span className={`badge ${overspend.is_overspend ? "badge-danger" : "badge-success"}`}
                  style={{ marginTop: 4, display: "inline-block" }}>
                  {overspend.is_overspend ? "과소비 주의" : "정상 범위"}
                </span>
              </div>
              <div style={{ marginTop: 16, display: "flex", justifyContent: "space-between" }}>
                <div>
                  <div className="stat-label">이번 달</div>
                  <div style={{ fontWeight: 600 }}>{formatKRW(overspend.monthly_total)}</div>
                </div>
                <div>
                  <div className="stat-label">월 평균</div>
                  <div style={{ fontWeight: 600 }}>{formatKRW(overspend.monthly_avg)}</div>
                </div>
                <div>
                  <div className="stat-label">분석 방법</div>
                  <div style={{ fontWeight: 600 }}>{overspend.method}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </>
  );
}

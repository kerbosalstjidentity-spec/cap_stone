"use client";

import { useState } from "react";
import Link from "next/link";

const CATEGORY_LABELS: Record<string, string> = {
  food: "식비", shopping: "쇼핑", transport: "교통", entertainment: "여가",
  education: "교육", healthcare: "의료", housing: "주거", utilities: "공과금",
  finance: "금융", travel: "여행", other: "기타",
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

  return (
    <>
      <nav>
        <div className="container">
          <h2>ConsumePattern</h2>
          <Link href="/dashboard">대시보드</Link>
          <Link href="/analysis" className="active">패턴 분석</Link>
          <Link href="/strategy">전략 제안</Link>
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
          {/* K-Means 군집 분석 */}
          {pattern && (
            <div className="card">
              <h3>소비 유형 (K-Means)</h3>
              <div style={{ margin: "16px 0" }}>
                <span className={`badge ${clusterBadge(pattern.cluster_label)}`} style={{ fontSize: 18, padding: "8px 20px" }}>
                  {pattern.cluster_label}
                </span>
              </div>
              <p className="text-secondary">
                총 {pattern.tx_count}건, 평균 {formatKRW(pattern.avg_amount)}/건
              </p>
              <p className="text-secondary">
                주 카테고리: {CATEGORY_LABELS[pattern.top_category] || pattern.top_category}
              </p>
            </div>
          )}

          {/* Isolation Forest 이상 탐지 */}
          {anomalies && (
            <div className="card">
              <h3>이상 지출 탐지 (Isolation Forest)</h3>
              <div style={{ margin: "16px 0" }}>
                <span className={`badge ${anomalies.anomaly_count > 0 ? "badge-danger" : "badge-success"}`}
                  style={{ fontSize: 16, padding: "6px 16px" }}>
                  {anomalies.anomaly_count > 0 ? `${anomalies.anomaly_count}건 감지` : "이상 없음"}
                </span>
              </div>
              <p className="text-secondary">전체 {anomalies.total_transactions}건 중 분석</p>
              {anomalies.anomalies?.slice(0, 5).map((a: any, i: number) => (
                <div key={i} style={{ marginTop: 8, padding: 8, background: "#fef2f2", borderRadius: 8 }}>
                  <span className="text-danger">{formatKRW(a.amount)}</span>
                  <span className="text-secondary"> — {a.reason}</span>
                </div>
              ))}
            </div>
          )}

          {/* LSTM 예측 */}
          {forecast && (
            <div className="card">
              <h3>다음 달 지출 예측 (LSTM)</h3>
              <div style={{ margin: "16px 0" }}>
                <div className="stat-value">{formatKRW(forecast.predicted_total)}</div>
                <p className="text-secondary" style={{ marginTop: 4 }}>
                  신뢰도: {(forecast.confidence * 100).toFixed(0)}%
                </p>
              </div>
              {Object.entries(forecast.predicted_by_category || {}).map(([cat, amt]) => (
                <div key={cat} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                  <span>{CATEGORY_LABELS[cat] || cat}</span>
                  <span>{formatKRW(amt as number)}</span>
                </div>
              ))}
            </div>
          )}

          {/* XGBoost 과소비 확률 */}
          {overspend && (
            <div className="card">
              <h3>과소비 위험도 (XGBoost)</h3>
              <div style={{ margin: "16px 0" }}>
                <div className="stat-value" style={{
                  color: overspend.is_overspend ? "var(--danger)" : "var(--success)"
                }}>
                  {(overspend.overspend_probability * 100).toFixed(1)}%
                </div>
                <span className={`badge ${overspend.is_overspend ? "badge-danger" : "badge-success"}`}>
                  {overspend.is_overspend ? "과소비 주의" : "정상"}
                </span>
              </div>
              <p className="text-secondary">
                이번 달: {formatKRW(overspend.monthly_total)} / 월평균: {formatKRW(overspend.monthly_avg)}
              </p>
              <p className="text-secondary">분석 방법: {overspend.method}</p>
            </div>
          )}
        </div>
      </main>
    </>
  );
}

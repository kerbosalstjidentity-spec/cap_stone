"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import NavBar from "@/components/NavBar";
import ShapWaterfall from "@/components/ShapWaterfall";
import { useAuth } from "@/hooks/useAuth";
import Link from "next/link";

interface ShapResult {
  user_id: string;
  base_value: number;
  prediction: number;
  is_overspend: boolean;
  features: { feature: string; feature_kr: string; value: number; shap_value: number }[];
  top_factor: string;
  top_factor_kr: string;
  summary_text: string;
  method: string;
}

interface AnomalyExplanation {
  transaction_id: string;
  amount: number;
  category: string;
  anomaly_score: number;
  contributions: { feature: string; feature_kr: string; deviation: number }[];
  top_factor_kr: string;
  reason: string;
}

interface ClusterResult {
  user_id: string;
  cluster_label: string;
  feature_deviations: { category: string; category_kr: string; user_value: number; center_value: number; deviation: number }[];
  summary_text: string;
  top_pull_toward: string;
  top_pull_away: string;
}

function XaiContent() {
  const { userId } = useAuth();
  const [overspend, setOverspend] = useState<ShapResult | null>(null);
  const [anomalies, setAnomalies] = useState<{ explanations: AnomalyExplanation[]; total_anomalies: number } | null>(null);
  const [cluster, setCluster] = useState<ClusterResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  async function runAnalysis() {
    if (!userId) return;
    setLoading(true);
    try {
      const [oRes, aRes, cRes] = await Promise.all([
        fetch(`/api/v1/xai/overspend/${userId}`).then(r => r.json()),
        fetch(`/api/v1/xai/anomalies/${userId}`).then(r => r.json()),
        fetch(`/api/v1/xai/cluster/${userId}`).then(r => r.json()),
      ]);
      setOverspend(oRes);
      setAnomalies(aRes);
      setCluster(cRes);
      setLoaded(true);
    } finally {
      setLoading(false);
    }
  }

  const riskColor = overspend
    ? overspend.prediction >= 0.7 ? "#ef4444" : overspend.prediction >= 0.4 ? "#f59e0b" : "#10b981"
    : "#6b7280";

  return (
    <>
      <NavBar activePath="/analysis" />
      <main className="container">
        {/* 서브 네비 */}
        <div style={{ display: "flex", gap: 8, marginBottom: 24, borderBottom: "2px solid var(--border)", paddingBottom: 12 }}>
          <Link href="/analysis" style={{ fontSize: 14, color: "#6b7280", padding: "4px 12px", borderRadius: 6 }}>분석 홈</Link>
          <Link href="/analysis/explain" style={{ fontSize: 14, color: "#6366f1", fontWeight: 700, padding: "4px 12px", borderRadius: 6, background: "#eef2ff" }}>AI 설명</Link>
          <Link href="/analysis/emotion" style={{ fontSize: 14, color: "#6b7280", padding: "4px 12px", borderRadius: 6 }}>감정 분석</Link>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>AI 설명 가능 분석</h1>
            <p className="text-secondary">ML 모델이 왜 그런 판단을 했는지 투명하게 설명합니다.</p>
          </div>
          <button
            onClick={runAnalysis}
            disabled={loading}
            style={{
              padding: "10px 24px", background: "#6366f1", color: "#fff",
              border: "none", borderRadius: 8, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "분석 중..." : loaded ? "다시 분석" : "XAI 분석 실행"}
          </button>
        </div>

        {!loaded && !loading && (
          <div className="card" style={{ textAlign: "center", padding: "48px 24px", color: "#9ca3af" }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🧠</div>
            <p style={{ fontWeight: 600, marginBottom: 8 }}>AI 설명 분석 준비 완료</p>
            <p style={{ fontSize: 14 }}>위 버튼을 클릭하면 SHAP, Feature Attribution, 군집 설명이 생성됩니다.</p>
          </div>
        )}

        {loaded && (
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

            {/* Section 1: 과소비 위험 SHAP */}
            <div className="card">
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
                <h2 style={{ margin: 0 }}>과소비 위험 설명</h2>
                {overspend && (
                  <span style={{
                    padding: "4px 14px", borderRadius: 20, fontSize: 13, fontWeight: 700,
                    background: riskColor + "20", color: riskColor,
                  }}>
                    {(overspend.prediction * 100).toFixed(0)}% 위험
                  </span>
                )}
                {overspend?.method === "shap" && (
                  <span style={{ fontSize: 12, color: "#9ca3af", marginLeft: "auto" }}>SHAP TreeExplainer</span>
                )}
              </div>

              {overspend?.summary_text && (
                <div style={{
                  padding: "12px 16px", background: "#f8fafc", borderRadius: 8,
                  borderLeft: `4px solid ${riskColor}`, marginBottom: 20,
                  fontSize: 14, fontWeight: 500,
                }}>
                  {overspend.summary_text}
                </div>
              )}

              {overspend?.features && overspend.features.length > 0 ? (
                <ShapWaterfall
                  features={overspend.features}
                  baseValue={overspend.base_value}
                  prediction={overspend.prediction}
                />
              ) : (
                <p className="text-secondary" style={{ textAlign: "center", padding: 16 }}>
                  {overspend?.method === "unavailable" ? "모델 학습 후 SHAP 분석이 가능합니다." : "데이터가 없습니다."}
                </p>
              )}
            </div>

            {/* Section 2: 이상거래 설명 */}
            <div className="card">
              <h2 style={{ marginBottom: 8 }}>이상 거래 설명</h2>
              <p className="text-secondary" style={{ marginBottom: 20, fontSize: 14 }}>
                Isolation Forest가 탐지한 이상 거래의 원인을 feature별로 설명합니다.
              </p>

              {!anomalies?.explanations?.length ? (
                <div style={{ textAlign: "center", padding: 24, color: "#9ca3af" }}>
                  감지된 이상 거래가 없거나 데이터가 없습니다.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {anomalies.explanations.map((expl, i) => (
                    <div key={i} style={{
                      border: "1px solid #fee2e2", borderRadius: 10, padding: 16,
                      background: "#fef2f2",
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                        <span style={{ fontWeight: 600, fontSize: 14 }}>
                          {expl.amount.toLocaleString("ko-KR")}원 · {expl.category}
                        </span>
                        <span style={{ fontSize: 12, color: "#ef4444", fontWeight: 600 }}>
                          이상 점수: {expl.anomaly_score.toFixed(3)}
                        </span>
                      </div>
                      <p style={{ fontSize: 13, color: "#374151", marginBottom: 10 }}>{expl.reason}</p>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {expl.contributions.slice(0, 4).map((c, j) => (
                          <span key={j} style={{
                            padding: "3px 10px", borderRadius: 12, fontSize: 11,
                            background: Math.abs(c.deviation) > 2 ? "#fee2e2" : "#f1f5f9",
                            color: Math.abs(c.deviation) > 2 ? "#dc2626" : "#6b7280",
                            fontWeight: Math.abs(c.deviation) > 2 ? 700 : 400,
                          }}>
                            {c.feature_kr}: {c.deviation > 0 ? "+" : ""}{c.deviation.toFixed(2)}σ
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Section 3: 군집 설명 */}
            {cluster && (
              <div className="card">
                <h2 style={{ marginBottom: 8 }}>소비 유형 분류 설명</h2>
                <p className="text-secondary" style={{ marginBottom: 16, fontSize: 14 }}>
                  K-Means가 분류한 소비 유형과 그 이유를 설명합니다.
                </p>
                <div style={{
                  padding: "12px 16px", background: "#eef2ff", borderRadius: 8,
                  borderLeft: "4px solid #6366f1", marginBottom: 16, fontSize: 14,
                }}>
                  <strong>"{cluster.cluster_label}"</strong> — {cluster.summary_text}
                </div>
                {cluster.feature_deviations.slice(0, 6).length > 0 && (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {cluster.feature_deviations.slice(0, 6).map((d, i) => (
                      <div key={i} style={{
                        padding: "8px 14px", borderRadius: 8, fontSize: 13,
                        background: d.deviation > 0 ? "#fef2f2" : "#f0fdf4",
                        border: `1px solid ${d.deviation > 0 ? "#fca5a5" : "#86efac"}`,
                      }}>
                        <span style={{ fontWeight: 600 }}>{d.category_kr}</span>{" "}
                        <span style={{ color: d.deviation > 0 ? "#dc2626" : "#16a34a" }}>
                          {d.deviation > 0 ? "▲" : "▼"} {Math.abs(d.deviation * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

          </div>
        )}
      </main>
    </>
  );
}

export default function ExplainPage() {
  return (
    <AuthGuard>
      <XaiContent />
    </AuthGuard>
  );
}

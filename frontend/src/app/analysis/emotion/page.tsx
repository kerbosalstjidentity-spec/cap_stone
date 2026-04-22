"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import NavBar from "@/components/NavBar";
import EmotionHeatmap from "@/components/EmotionHeatmap";
import EmotionTagDialog from "@/components/EmotionTagDialog";
import { useAuth } from "@/hooks/useAuth";
import Link from "next/link";

const RISK_COLORS = { safe: "#10b981", caution: "#f59e0b", warning: "#f97316", danger: "#ef4444" };
const RISK_KR = { safe: "안전", caution: "주의", warning: "경고", danger: "위험" };

function EmotionContent() {
  const { userId } = useAuth();
  const [heatmap, setHeatmap] = useState<any>(null);
  const [impulse, setImpulse] = useState<any>(null);
  const [insights, setInsights] = useState<any[]>([]);
  const [recentTxs, setRecentTxs] = useState<any[]>([]);
  const [tags, setTags] = useState<any[]>([]);
  const [tagDialog, setTagDialog] = useState<{ txId: string; info: string } | null>(null);
  const [loading, setLoading] = useState(false);

  async function fetchAll() {
    if (!userId) return;
    setLoading(true);
    try {
      const [hRes, iRes, insRes, tagRes, txRes] = await Promise.all([
        fetch(`/api/v1/emotion/heatmap/${userId}`).then(r => r.json()),
        fetch(`/api/v1/emotion/impulse-risk/${userId}`).then(r => r.json()),
        fetch(`/api/v1/emotion/insights/${userId}`).then(r => r.json()),
        fetch(`/api/v1/emotion/tags/${userId}?limit=20`).then(r => r.json()),
        fetch(`/api/v1/profile/${userId}`).then(r => r.json()),
      ]);
      setHeatmap(hRes);
      setImpulse(iRes);
      setInsights(insRes?.insights ?? []);
      setTags(tagRes?.tags ?? []);
      // 최근 거래 (프로필에서 추출 불가 → 분석 API 사용)
    } finally {
      setLoading(false);
    }
  }

  async function fetchRecentTxs() {
    if (!userId) return;
    try {
      const res = await fetch(`/api/v1/emotion/recent-transactions/${userId}?limit=20`).then(r => r.json());
      setRecentTxs(res?.transactions ?? []);
    } catch { /* silent */ }
  }

  useEffect(() => {
    if (userId) {
      fetchAll();
      fetchRecentTxs();
    }
  }, [userId]);

  const riskLevel = (impulse?.risk_level ?? "safe") as keyof typeof RISK_COLORS;
  const riskScore = impulse?.risk_score ?? 0;

  // SVG 게이지
  const angle = riskScore * 180 - 90;
  const rad = (angle * Math.PI) / 180;
  const cx = 80, cy = 70, r = 55;
  const nx = cx + r * Math.cos(rad);
  const ny = cy + r * Math.sin(rad);

  const taggedIds = new Set(tags.map((t: any) => t.transaction_id));

  return (
    <>
      <NavBar activePath="/analysis" />
      <main className="container">
        {/* 서브 네비 */}
        <div style={{ display: "flex", gap: 8, marginBottom: 24, borderBottom: "2px solid var(--border)", paddingBottom: 12 }}>
          <Link href="/analysis" style={{ fontSize: 14, color: "#6b7280", padding: "4px 12px", borderRadius: 6 }}>분석 홈</Link>
          <Link href="/analysis/explain" style={{ fontSize: 14, color: "#6b7280", padding: "4px 12px", borderRadius: 6 }}>AI 설명</Link>
          <Link href="/analysis/emotion" style={{ fontSize: 14, color: "#6366f1", fontWeight: 700, padding: "4px 12px", borderRadius: 6, background: "#eef2ff" }}>감정 분석</Link>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>감정×소비 분석</h1>
            <p className="text-secondary">감정 상태와 소비 패턴의 상관관계를 분석합니다.</p>
          </div>
          <button onClick={fetchAll} disabled={loading} style={{
            padding: "8px 20px", background: "#6366f1", color: "#fff",
            border: "none", borderRadius: 8, cursor: loading ? "not-allowed" : "pointer",
            fontWeight: 600, opacity: loading ? 0.7 : 1,
          }}>
            {loading ? "로딩 중..." : "새로고침"}
          </button>
        </div>

        <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 24, marginBottom: 24 }}>

          {/* 충동 소비 위험 게이지 */}
          <div className="card">
            <h3 style={{ marginBottom: 16 }}>현재 충동 소비 위험도</h3>
            <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
              <svg width={160} height={90} viewBox="0 0 160 90">
                {/* 배경 반원 */}
                <path d="M 25 70 A 55 55 0 0 1 135 70" fill="none" stroke="#e2e8f0" strokeWidth={12} />
                {/* 색상 반원 */}
                <path d="M 25 70 A 55 55 0 0 1 135 70" fill="none"
                  stroke={RISK_COLORS[riskLevel]} strokeWidth={12}
                  strokeDasharray={`${riskScore * 172.8} 172.8`}
                  strokeLinecap="round" />
                {/* 바늘 */}
                <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#374151" strokeWidth={3} strokeLinecap="round" />
                <circle cx={cx} cy={cy} r={4} fill="#374151" />
                {/* 수치 */}
                <text x={cx} y={cy + 20} textAnchor="middle" fontSize={18} fontWeight={700} fill={RISK_COLORS[riskLevel]}>
                  {(riskScore * 100).toFixed(0)}
                </text>
              </svg>
              <div>
                <div style={{
                  display: "inline-block", padding: "4px 14px", borderRadius: 20,
                  background: RISK_COLORS[riskLevel] + "20", color: RISK_COLORS[riskLevel],
                  fontWeight: 700, fontSize: 15, marginBottom: 8,
                }}>
                  {RISK_KR[riskLevel]}
                </div>
                <p style={{ fontSize: 13, color: "#374151", maxWidth: 160 }}>{impulse?.warning_message}</p>
                <p style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>
                  {impulse?.current_day}요일 {impulse?.current_hour}시
                </p>
              </div>
            </div>
            {impulse?.risk_factors?.length > 0 && (
              <div style={{ marginTop: 12, borderTop: "1px solid #f1f5f9", paddingTop: 12 }}>
                {impulse.risk_factors.map((f: any, i: number) => (
                  <p key={i} style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>• {f.description}</p>
                ))}
              </div>
            )}
          </div>

          {/* 인사이트 카드 */}
          <div className="card">
            <h3 style={{ marginBottom: 16 }}>감정 소비 인사이트</h3>
            {insights.length === 0 ? (
              <p style={{ color: "#9ca3af", fontSize: 14, textAlign: "center", padding: "16px 0" }}>
                감정 태그를 추가하면 인사이트가 표시됩니다.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {insights.slice(0, 4).map((ins, i) => (
                  <div key={i} style={{
                    padding: "10px 14px", borderRadius: 8,
                    background: ins.severity === "danger" ? "#fef2f2" : ins.severity === "warning" ? "#fffbeb" : "#f0f9ff",
                    borderLeft: `3px solid ${ins.severity === "danger" ? "#ef4444" : ins.severity === "warning" ? "#f59e0b" : "#3b82f6"}`,
                    fontSize: 13,
                  }}>
                    {ins.insight_text}
                    <span style={{
                      marginLeft: 8, fontSize: 11,
                      color: ins.severity === "danger" ? "#ef4444" : "#f59e0b",
                      fontWeight: 700,
                    }}>×{ins.multiplier}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 감정×카테고리 히트맵 */}
        <div className="card" style={{ marginBottom: 24 }}>
          <h3 style={{ marginBottom: 16 }}>감정×카테고리 지출 히트맵</h3>
          <EmotionHeatmap rows={heatmap?.rows ?? []} />
        </div>

        {/* 감정 태깅 */}
        <div className="card">
          <h3 style={{ marginBottom: 8 }}>거래 감정 태깅</h3>
          <p className="text-secondary" style={{ marginBottom: 16, fontSize: 14 }}>
            최근 거래에 감정을 태깅하면 소비 패턴과 감정의 상관관계를 분석합니다.
          </p>
          {recentTxs.length === 0 ? (
            <p style={{ color: "#9ca3af", fontSize: 14 }}>거래 데이터가 없습니다. 대시보드에서 데모 데이터를 생성하세요.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {recentTxs.slice(0, 12).map((tx, i) => {
                const tag = tags.find((t: any) => t.transaction_id === tx.transaction_id);
                return (
                  <div key={i} style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "10px 14px", border: "1px solid #e5e7eb", borderRadius: 8,
                    background: taggedIds.has(tx.transaction_id) ? "#f0fdf4" : "#fff",
                  }}>
                    <div>
                      <span style={{ fontWeight: 600 }}>{tx.amount.toLocaleString("ko-KR")}원</span>
                      <span style={{ fontSize: 12, color: "#6b7280", marginLeft: 8 }}>{tx.category}</span>
                      {tag && (
                        <span style={{
                          marginLeft: 8, fontSize: 11, padding: "2px 8px", borderRadius: 10,
                          background: "#eef2ff", color: "#6366f1", fontWeight: 600,
                        }}>
                          {tag.emotion_kr ?? tag.emotion}
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => setTagDialog({
                        txId: tx.transaction_id,
                        info: `${tx.amount.toLocaleString("ko-KR")}원 · ${tx.category}`,
                      })}
                      style={{
                        padding: "5px 14px", background: tag ? "#f0fdf4" : "#6366f1",
                        color: tag ? "#16a34a" : "#fff",
                        border: `1px solid ${tag ? "#86efac" : "transparent"}`,
                        borderRadius: 6, cursor: "pointer", fontSize: 12, fontWeight: 600,
                      }}
                    >
                      {tag ? "수정" : "태깅"}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 태그 다이얼로그 */}
        {tagDialog && userId && (
          <EmotionTagDialog
            userId={userId}
            transactionId={tagDialog.txId}
            transactionInfo={tagDialog.info}
            onSave={() => { fetchAll(); setTagDialog(null); }}
            onClose={() => setTagDialog(null)}
          />
        )}
      </main>
    </>
  );
}

export default function EmotionPage() {
  return (
    <AuthGuard>
      <EmotionContent />
    </AuthGuard>
  );
}

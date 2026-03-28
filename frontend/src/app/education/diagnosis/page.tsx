"use client";

import { useState } from "react";
import Link from "next/link";

const CATEGORY_LABELS: Record<string, string> = {
  food: "식비", shopping: "쇼핑", transport: "교통", entertainment: "여가",
  education: "교육", healthcare: "의료", housing: "주거", utilities: "공과금",
  finance: "금융", travel: "여행", other: "기타",
};

const RISK_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  safe: { label: "안전", color: "#22c55e", bg: "#f0fdf4" },
  caution: { label: "주의", color: "#f59e0b", bg: "#fffbeb" },
  warning: { label: "경고", color: "#f97316", bg: "#fff7ed" },
  danger: { label: "위험", color: "#ef4444", bg: "#fef2f2" },
  critical: { label: "심각", color: "#dc2626", bg: "#fef2f2" },
};

const LEVEL_LABELS: Record<string, string> = {
  beginner: "기초반", intermediate: "중급반", advanced: "고급반",
};

export default function DiagnosisPage() {
  const [userId, setUserId] = useState("demo_user");
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchDiagnosis = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`/api/v1/education/diagnosis/${userId}`);
      const data = await res.json();
      if (res.ok) setReport(data);
      else setError(data.detail || "진단 데이터를 불러올 수 없습니다.");
    } catch {
      setError("서버에 연결할 수 없습니다.");
    } finally {
      setLoading(false);
    }
  };

  const risk = report ? RISK_CONFIG[report.risk_grade] : null;

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
          <h1>소비 습관 진단</h1>
          <input
            value={userId} onChange={(e) => setUserId(e.target.value)}
            style={{ padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8 }}
          />
          <button onClick={fetchDiagnosis} disabled={loading} style={{
            padding: "8px 20px", background: "var(--primary)", color: "#fff",
            border: "none", borderRadius: 8, cursor: "pointer",
          }}>
            {loading ? "진단 중..." : "진단 시작"}
          </button>
        </div>

        {error && <div className="card" style={{ color: "var(--danger)", marginBottom: 16 }}>{error}</div>}

        {report && risk && (
          <div className="grid grid-2">
            {/* 소비 유형 카드 */}
            <div className="card" style={{ borderTop: "4px solid var(--primary)" }}>
              <div style={{ textAlign: "center", padding: "16px 0" }}>
                <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 8 }}>당신의 소비 유형</div>
                <div style={{
                  display: "inline-block", padding: "12px 32px", borderRadius: 12,
                  background: "#eef2ff", fontSize: 28, fontWeight: 700, color: "var(--primary)",
                }}>
                  {report.spend_type}
                </div>
                <p style={{ marginTop: 16, fontSize: 15, lineHeight: 1.7, color: "var(--text-secondary)" }}>
                  {report.spend_type_description}
                </p>
              </div>
            </div>

            {/* 위험도 카드 */}
            <div className="card" style={{ borderTop: `4px solid ${risk.color}` }}>
              <div style={{ textAlign: "center", padding: "16px 0" }}>
                <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 8 }}>과소비 위험도</div>
                <div style={{ position: "relative", width: 160, height: 160, margin: "0 auto" }}>
                  <svg viewBox="0 0 160 160" style={{ transform: "rotate(-90deg)" }}>
                    <circle cx="80" cy="80" r="70" fill="none" stroke="#e2e8f0" strokeWidth="12" />
                    <circle cx="80" cy="80" r="70" fill="none" stroke={risk.color} strokeWidth="12"
                      strokeDasharray={`${report.risk_score * 440} 440`}
                      strokeLinecap="round" />
                  </svg>
                  <div style={{
                    position: "absolute", inset: 0, display: "flex", flexDirection: "column",
                    alignItems: "center", justifyContent: "center",
                  }}>
                    <span style={{ fontSize: 32, fontWeight: 700, color: risk.color }}>
                      {(report.risk_score * 100).toFixed(0)}%
                    </span>
                    <span style={{
                      padding: "2px 12px", borderRadius: 12, fontSize: 13,
                      background: risk.bg, color: risk.color, fontWeight: 600,
                    }}>
                      {risk.label}
                    </span>
                  </div>
                </div>
                <p style={{ marginTop: 12, fontSize: 14, color: "var(--text-secondary)" }}>
                  {report.risk_description}
                </p>
              </div>
            </div>

            {/* 전월 비교 인사이트 */}
            <div className="card">
              <h3 style={{ marginBottom: 12 }}>전월 비교</h3>
              <div style={{
                padding: "16px", borderRadius: 8, background: "#f8fafc",
                borderLeft: "4px solid var(--primary)", fontSize: 15, lineHeight: 1.7,
              }}>
                {report.monthly_insight}
              </div>
            </div>

            {/* 이상 소비 */}
            <div className="card">
              <h3 style={{ marginBottom: 12 }}>
                이상 소비 감지
                <span className="badge badge-warning" style={{ marginLeft: 8 }}>
                  {report.anomaly_count}건
                </span>
              </h3>
              {report.anomaly_highlights.length > 0 ? (
                report.anomaly_highlights.map((h: string, i: number) => (
                  <div key={i} style={{
                    padding: "10px 14px", margin: "8px 0", borderRadius: 8,
                    background: "#fffbeb", borderLeft: "3px solid var(--warning)", fontSize: 14,
                  }}>
                    {h}
                  </div>
                ))
              ) : (
                <p className="text-secondary">이상 소비가 감지되지 않았습니다.</p>
              )}
            </div>

            {/* 개선 포인트 */}
            <div className="card" style={{ gridColumn: "1 / -1" }}>
              <h3 style={{ marginBottom: 16 }}>개선 포인트</h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12 }}>
                {report.improvement_points.map((p: string, i: number) => (
                  <div key={i} style={{
                    padding: "14px 18px", borderRadius: 8,
                    background: "#f0fdf4", borderLeft: "3px solid var(--success)",
                    fontSize: 14, lineHeight: 1.6,
                  }}>
                    {p}
                  </div>
                ))}
              </div>
            </div>

            {/* 추천 학습 */}
            <div className="card" style={{ gridColumn: "1 / -1" }}>
              <h3 style={{ marginBottom: 16 }}>
                추천 학습 레벨:
                <span className="badge badge-primary" style={{ marginLeft: 8, fontSize: 14 }}>
                  {LEVEL_LABELS[report.recommended_level] || report.recommended_level}
                </span>
              </h3>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {report.recommended_courses.map((c: string, i: number) => (
                  <span key={i} style={{
                    padding: "8px 16px", borderRadius: 8, background: "#eef2ff",
                    color: "var(--primary)", fontSize: 14,
                  }}>
                    {c}
                  </span>
                ))}
              </div>
              <div style={{ marginTop: 16 }}>
                <Link href="/education/course" style={{
                  display: "inline-block", padding: "10px 24px",
                  background: "var(--primary)", color: "#fff",
                  borderRadius: 8, textDecoration: "none", fontSize: 14,
                }}>
                  코스 시작하기
                </Link>
              </div>
            </div>
          </div>
        )}

        {!report && !loading && !error && (
          <div className="card" style={{ textAlign: "center", padding: 48 }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>&#x1F50D;</div>
            <p className="text-secondary">사용자 ID를 입력하고 진단을 시작하세요.</p>
            <p className="text-secondary" style={{ fontSize: 13, marginTop: 8 }}>
              대시보드에서 먼저 데모 데이터를 생성해야 합니다.
            </p>
          </div>
        )}
      </main>
    </>
  );
}

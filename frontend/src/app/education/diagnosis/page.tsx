"use client";

import { useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/hooks/useAuth";

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

function DiagnosisContent() {
  const { userId } = useAuth();
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchDiagnosis = async () => {
    if (!userId) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`/api/v1/education/diagnosis/${userId}`);
      let data: any;
      try { data = await res.json(); } catch { data = {}; }
      if (res.ok) setReport(data);
      else if (res.status === 404) setError("소비 데이터가 없습니다. 먼저 대시보드에서 '데모 데이터 생성' 버튼을 눌러주세요.");
      else setError(data.detail || "진단 데이터를 불러올 수 없습니다.");
    } catch {
      setError("서버에 연결할 수 없습니다. 백엔드 서버(포트 8020)가 실행 중인지 확인하세요.");
    } finally {
      setLoading(false);
    }
  };

  const risk = report ? RISK_CONFIG[report.risk_grade] : null;

  return (
    <>
      <NavBar activePath="/education" />
      <main className="container">
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
          <h1>소비 습관 진단</h1>
          <button onClick={fetchDiagnosis} disabled={loading} style={{
            padding: "8px 20px", background: "var(--primary)", color: "#fff",
            border: "none", borderRadius: 8, cursor: "pointer", opacity: loading ? 0.7 : 1,
          }}>
            {loading ? "진단 중..." : "진단 시작"}
          </button>
        </div>

        {error && <div className="card" style={{ color: "var(--danger)", marginBottom: 16 }}>{error}</div>}

        {report && risk && (
          <div className="grid grid-2">
            <div className="card" style={{ borderTop: "4px solid var(--primary)" }}>
              <div style={{ textAlign: "center", padding: "16px 0" }}>
                <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 8 }}>당신의 소비 유형</div>
                <div style={{ display: "inline-block", padding: "12px 32px", borderRadius: 12, background: "#eef2ff", fontSize: 28, fontWeight: 700, color: "var(--primary)" }}>
                  {report.spend_type}
                </div>
                <p style={{ marginTop: 16, fontSize: 15, lineHeight: 1.7, color: "var(--text-secondary)" }}>{report.spend_type_description}</p>
              </div>
            </div>

            <div className="card" style={{ borderTop: `4px solid ${risk.color}` }}>
              <div style={{ textAlign: "center", padding: "16px 0" }}>
                <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 8 }}>과소비 위험도</div>
                <div style={{ position: "relative", width: 160, height: 160, margin: "0 auto" }}>
                  <svg viewBox="0 0 160 160" style={{ transform: "rotate(-90deg)" }}>
                    <circle cx="80" cy="80" r="70" fill="none" stroke="#e2e8f0" strokeWidth="12" />
                    <circle cx="80" cy="80" r="70" fill="none" stroke={risk.color} strokeWidth="12"
                      strokeDasharray={`${report.risk_score * 440} 440`} strokeLinecap="round" />
                  </svg>
                  <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                    <span style={{ fontSize: 32, fontWeight: 700, color: risk.color }}>{(report.risk_score * 100).toFixed(0)}%</span>
                    <span style={{ padding: "2px 12px", borderRadius: 12, fontSize: 13, background: risk.bg, color: risk.color, fontWeight: 600 }}>{risk.label}</span>
                  </div>
                </div>
                <p style={{ marginTop: 12, fontSize: 14, color: "var(--text-secondary)" }}>{report.risk_description}</p>
              </div>
            </div>

            <div className="card">
              <h3 style={{ marginBottom: 12 }}>전월 비교</h3>
              <div style={{ padding: "16px", borderRadius: 8, background: "#f8fafc", borderLeft: "4px solid var(--primary)", fontSize: 15, lineHeight: 1.7 }}>
                {report.monthly_insight}
              </div>
            </div>

            <div className="card">
              <h3 style={{ marginBottom: 12 }}>이상 소비 감지 <span className="badge badge-warning" style={{ marginLeft: 8 }}>{report.anomaly_count}건</span></h3>
              {report.anomaly_highlights.length > 0 ? (
                report.anomaly_highlights.map((h: string, i: number) => (
                  <div key={i} style={{ padding: "10px 14px", margin: "8px 0", borderRadius: 8, background: "#fffbeb", borderLeft: "3px solid var(--warning)", fontSize: 14 }}>
                    {h}
                  </div>
                ))
              ) : (
                <p className="text-secondary">이상 소비가 감지되지 않았습니다.</p>
              )}
            </div>

            <div className="card" style={{ gridColumn: "1 / -1" }}>
              <h3 style={{ marginBottom: 16 }}>개선 포인트</h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12 }}>
                {report.improvement_points.map((p: string, i: number) => (
                  <div key={i} style={{ padding: "14px 18px", borderRadius: 8, background: "#f0fdf4", borderLeft: "3px solid var(--success)", fontSize: 14, lineHeight: 1.6 }}>
                    {p}
                  </div>
                ))}
              </div>
            </div>

            <div className="card" style={{ gridColumn: "1 / -1" }}>
              <h3 style={{ marginBottom: 16 }}>
                추천 학습 레벨: <span className="badge badge-primary" style={{ marginLeft: 8, fontSize: 14 }}>{LEVEL_LABELS[report.recommended_level] || report.recommended_level}</span>
              </h3>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {report.recommended_courses.map((c: string, i: number) => (
                  <span key={i} style={{ padding: "8px 16px", borderRadius: 8, background: "#eef2ff", color: "var(--primary)", fontSize: 14 }}>{c}</span>
                ))}
              </div>
              <div style={{ marginTop: 16 }}>
                <Link href="/education/course" style={{ display: "inline-block", padding: "10px 24px", background: "var(--primary)", color: "#fff", borderRadius: 8, textDecoration: "none", fontSize: 14 }}>
                  코스 시작하기
                </Link>
              </div>
            </div>
          </div>
        )}

        {!report && !loading && !error && (
          <div className="card" style={{ textAlign: "center", padding: 48 }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🔍</div>
            <p className="text-secondary">진단 시작 버튼을 눌러 내 소비 습관을 분석하세요.</p>
            <p className="text-secondary" style={{ fontSize: 13, marginTop: 8 }}>대시보드에서 먼저 데모 데이터를 생성해야 합니다.</p>
          </div>
        )}
      </main>
    </>
  );
}

export default function DiagnosisPage() {
  return (
    <AuthGuard>
      <DiagnosisContent />
    </AuthGuard>
  );
}

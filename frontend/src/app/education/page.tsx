"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/hooks/useAuth";

const LEVEL_INFO: Record<string, { label: string; color: string; bg: string }> = {
  beginner: { label: "기초반", color: "#22c55e", bg: "#f0fdf4" },
  intermediate: { label: "중급반", color: "#f59e0b", bg: "#fffbeb" },
  advanced: { label: "고급반", color: "#8b5cf6", bg: "#f5f3ff" },
};

function EducationContent() {
  const { userId } = useAuth();
  const [curriculum, setCurriculum] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const fetchCurriculum = async () => {
    if (!userId) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/education/curriculum/${userId}`);
      if (res.ok) setCurriculum(await res.json());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (userId) fetchCurriculum();
  }, [userId]);

  const level = curriculum ? LEVEL_INFO[curriculum.assigned_level] : null;

  return (
    <>
      <NavBar activePath="/education" />
      <main className="container">
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
          <h1>소비습관 코치</h1>
          <button onClick={fetchCurriculum} disabled={loading} style={{
            padding: "8px 20px", background: "var(--primary)", color: "#fff",
            border: "none", borderRadius: 8, cursor: "pointer", opacity: loading ? 0.7 : 1,
          }}>
            {loading ? "분석 중..." : "커리큘럼 새로고침"}
          </button>
        </div>

        {curriculum && level && (
          <div className="card" style={{ marginBottom: 24, borderLeft: `4px solid ${level.color}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
              <span style={{ padding: "6px 16px", borderRadius: 20, fontSize: 15, fontWeight: 600, background: level.bg, color: level.color }}>
                {level.label}
              </span>
              <span className="text-secondary">{curriculum.completed_courses}/{curriculum.total_courses} 코스 완료</span>
            </div>
            <p style={{ fontSize: 15 }}>{curriculum.reason}</p>
            <div style={{ marginTop: 12, height: 8, background: "var(--border)", borderRadius: 4, overflow: "hidden" }}>
              <div style={{
                height: "100%", borderRadius: 4, background: level.color,
                width: `${curriculum.total_courses > 0 ? (curriculum.completed_courses / curriculum.total_courses) * 100 : 0}%`,
                transition: "width 0.5s",
              }} />
            </div>
          </div>
        )}

        <div className="grid grid-3" style={{ marginBottom: 32 }}>
          {[
            { href: "/education/diagnosis", icon: "📋", title: "소비 습관 진단", desc: "AI 기반 종합 진단 리포트로\n내 소비 유형과 위험도를 확인하세요" },
            { href: "/education/course", icon: "📚", title: "맞춤 교육 코스", desc: "레벨별 단계적 학습으로\n소비 관리 역량을 키우세요" },
            { href: "/education/challenge", icon: "🏆", title: "챌린지 & 배지", desc: "절약 챌린지에 도전하고\n배지를 모아보세요" },
            { href: "/education/simulate", icon: "💰", title: "절약 시뮬레이션", desc: "\"만약에\" 시나리오로\n절약 효과를 미리 확인하세요" },
            { href: "/education/security", icon: "🔒", title: "보안 교육", desc: "사기 탐지 퀴즈와 시뮬레이터로\n금융 보안 감각을 키우세요" },
          ].map((item) => (
            <Link key={item.href} href={item.href} style={{ textDecoration: "none" }}>
              <div className="card" style={{ cursor: "pointer", minHeight: 160 }}>
                <div style={{ fontSize: 32, marginBottom: 12 }}>{item.icon}</div>
                <h3>{item.title}</h3>
                <p className="text-secondary" style={{ marginTop: 8, fontSize: 14, whiteSpace: "pre-line" }}>{item.desc}</p>
              </div>
            </Link>
          ))}
          <div className="card" style={{ minHeight: 160, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", background: "#f8fafc" }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>📊</div>
            <h3>리더보드</h3>
            <p className="text-secondary" style={{ marginTop: 8, fontSize: 14, textAlign: "center" }}>다른 사용자들과<br />학습 성과를 비교하세요</p>
          </div>
        </div>

        {curriculum && (
          <div>
            <h2 style={{ marginBottom: 16 }}>추천 코스</h2>
            <div className="grid grid-2">
              {curriculum.courses.map((course: any) => (
                <Link key={course.course_id} href={`/education/course?id=${course.course_id}`} style={{ textDecoration: "none" }}>
                  <div className="card" style={{ cursor: "pointer" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <span className="badge badge-primary">{level?.label}</span>
                      <span className="text-secondary" style={{ fontSize: 13 }}>{course.total_steps}단계</span>
                    </div>
                    <h3 style={{ marginBottom: 8 }}>{course.title}</h3>
                    <p className="text-secondary" style={{ fontSize: 14 }}>{course.description}</p>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}

        {!curriculum && !loading && (
          <div className="card" style={{ textAlign: "center", padding: 48 }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🎓</div>
            <p className="text-secondary">커리큘럼을 불러오는 중입니다...</p>
            <p className="text-secondary" style={{ fontSize: 13, marginTop: 8 }}>데이터가 없으면 대시보드에서 먼저 데모 데이터를 생성하세요.</p>
          </div>
        )}
      </main>
    </>
  );
}

export default function EducationHome() {
  return (
    <AuthGuard>
      <EducationContent />
    </AuthGuard>
  );
}

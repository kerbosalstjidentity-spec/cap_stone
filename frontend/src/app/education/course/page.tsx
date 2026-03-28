"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

const LEVEL_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  beginner: { label: "기초반", color: "#22c55e", bg: "#f0fdf4" },
  intermediate: { label: "중급반", color: "#f59e0b", bg: "#fffbeb" },
  advanced: { label: "고급반", color: "#8b5cf6", bg: "#f5f3ff" },
};

interface CourseStep {
  step: number;
  title: string;
  content: string;
  tip: string;
  interactive: string;
}

interface Course {
  course_id: string;
  level: string;
  title: string;
  description: string;
  steps: CourseStep[];
  total_steps: number;
}

export default function CoursePageWrapper() {
  return (
    <Suspense fallback={<div className="container" style={{ padding: 48, textAlign: "center" }}>로딩 중...</div>}>
      <CoursePage />
    </Suspense>
  );
}

function CoursePage() {
  const searchParams = useSearchParams();
  const courseIdParam = searchParams.get("id");

  const [userId, setUserId] = useState("demo_user");
  const [courses, setCourses] = useState<Course[]>([]);
  const [selectedCourse, setSelectedCourse] = useState<Course | null>(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [progress, setProgress] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/v1/education/courses")
      .then((r) => r.json())
      .then((data) => {
        setCourses(data.courses || []);
        if (courseIdParam) {
          const found = (data.courses || []).find((c: Course) => c.course_id === courseIdParam);
          if (found) {
            setSelectedCourse(found);
            setCurrentStep(0);
          }
        }
      });
  }, [courseIdParam]);

  const selectCourse = async (course: Course) => {
    setSelectedCourse(course);
    setCurrentStep(0);
    // 진행률 조회
    const res = await fetch(`/api/v1/education/course/${course.course_id}/progress/${userId}`);
    const data = await res.json();
    setProgress(data);
    if (data.progress?.current_step) {
      setCurrentStep(Math.min(data.progress.current_step - 1, course.steps.length - 1));
    }
  };

  const advanceStep = async () => {
    if (!selectedCourse) return;
    setLoading(true);
    // 서버에 진행률 업데이트
    await fetch(`/api/v1/education/course/${selectedCourse.course_id}/progress?user_id=${userId}`, {
      method: "POST",
    });
    if (currentStep < selectedCourse.steps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      // 완료
      const res = await fetch(`/api/v1/education/course/${selectedCourse.course_id}/progress/${userId}`);
      setProgress(await res.json());
    }
    setLoading(false);
  };

  const goBack = () => {
    if (currentStep > 0) setCurrentStep(currentStep - 1);
  };

  // 코스 목록을 레벨별로 그룹핑
  const grouped = courses.reduce<Record<string, Course[]>>((acc, c) => {
    if (!acc[c.level]) acc[c.level] = [];
    acc[c.level].push(c);
    return acc;
  }, {});

  const step = selectedCourse?.steps[currentStep];
  const levelConf = selectedCourse ? LEVEL_CONFIG[selectedCourse.level] : null;

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
          <h1>맞춤 교육 코스</h1>
          {selectedCourse && (
            <button onClick={() => setSelectedCourse(null)} style={{
              padding: "6px 16px", background: "#f1f5f9", color: "var(--text)",
              border: "1px solid var(--border)", borderRadius: 8, cursor: "pointer", fontSize: 13,
            }}>
              코스 목록으로
            </button>
          )}
          <div style={{ flex: 1 }} />
          <input
            value={userId} onChange={(e) => setUserId(e.target.value)}
            placeholder="User ID"
            style={{ padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8 }}
          />
        </div>

        {/* 코스 상세 보기 */}
        {selectedCourse && step && levelConf && (
          <div>
            {/* 코스 헤더 */}
            <div className="card" style={{ marginBottom: 24, borderTop: `4px solid ${levelConf.color}` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                <span style={{
                  padding: "4px 12px", borderRadius: 12, fontSize: 13, fontWeight: 600,
                  background: levelConf.bg, color: levelConf.color,
                }}>
                  {levelConf.label}
                </span>
                <h2 style={{ margin: 0 }}>{selectedCourse.title}</h2>
              </div>
              {/* 진행 바 */}
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ flex: 1, height: 8, background: "#e2e8f0", borderRadius: 4, overflow: "hidden" }}>
                  <div style={{
                    height: "100%", borderRadius: 4, background: levelConf.color,
                    width: `${((currentStep + 1) / selectedCourse.steps.length) * 100}%`,
                    transition: "width 0.3s",
                  }} />
                </div>
                <span className="text-secondary" style={{ fontSize: 13, whiteSpace: "nowrap" }}>
                  {currentStep + 1} / {selectedCourse.steps.length}
                </span>
              </div>
            </div>

            {/* 단계 네비게이션 */}
            <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
              {selectedCourse.steps.map((s, i) => (
                <button key={i} onClick={() => setCurrentStep(i)} style={{
                  padding: "6px 14px", borderRadius: 8, fontSize: 13, cursor: "pointer",
                  border: i === currentStep ? `2px solid ${levelConf.color}` : "1px solid var(--border)",
                  background: i === currentStep ? levelConf.bg : "#fff",
                  color: i === currentStep ? levelConf.color : "var(--text-secondary)",
                  fontWeight: i === currentStep ? 600 : 400,
                }}>
                  {i + 1}. {s.title}
                </button>
              ))}
            </div>

            {/* 학습 내용 */}
            <div className="card">
              <h3 style={{ marginBottom: 16, color: levelConf.color }}>
                Step {step.step}: {step.title}
              </h3>
              <div style={{ fontSize: 15, lineHeight: 1.8, marginBottom: 20, whiteSpace: "pre-line" }}>
                {step.content}
              </div>
              {step.tip && (
                <div style={{
                  padding: "14px 18px", borderRadius: 8, background: "#fffbeb",
                  borderLeft: "4px solid var(--warning)", marginBottom: 20,
                }}>
                  <strong style={{ color: "var(--warning)" }}>TIP</strong>
                  <span style={{ marginLeft: 8, fontSize: 14 }}>{step.tip}</span>
                </div>
              )}
              {step.interactive && (
                <div style={{
                  padding: "12px 16px", borderRadius: 8, background: "#eef2ff",
                  fontSize: 13, color: "var(--primary)",
                }}>
                  &#x1F517; 실습 연동: {step.interactive === "category_chart" && (
                    <Link href="/dashboard">대시보드에서 카테고리 차트 확인</Link>
                  )}
                  {step.interactive === "seed_demo" && (
                    <Link href="/dashboard">대시보드에서 데모 데이터 생성</Link>
                  )}
                  {step.interactive === "strategy_recommend" && (
                    <Link href="/strategy">전략 제안 페이지</Link>
                  )}
                  {step.interactive === "trend_chart" && (
                    <Link href="/dashboard">대시보드 월별 추이 차트</Link>
                  )}
                  {step.interactive === "diagnosis" && (
                    <Link href="/education/diagnosis">소비 습관 진단</Link>
                  )}
                  {step.interactive === "budget_api" && (
                    <Link href="/strategy">예산 설정 (전략 제안)</Link>
                  )}
                  {step.interactive === "pattern_analysis" && (
                    <Link href="/analysis">패턴 분석 페이지</Link>
                  )}
                  {step.interactive === "anomaly_analysis" && (
                    <Link href="/analysis">이상 탐지 분석</Link>
                  )}
                  {step.interactive === "savings_simulate" && (
                    <Link href="/education/simulate">절약 시뮬레이션</Link>
                  )}
                  {step.interactive === "forecast_analysis" && (
                    <Link href="/analysis">지출 예측 분석</Link>
                  )}
                  {step.interactive === "fraud_quiz" && (
                    <Link href="/education/security">사기 탐지 퀴즈</Link>
                  )}
                  {step.interactive === "fraud_simulate" && (
                    <Link href="/education/security">사기 시뮬레이터</Link>
                  )}
                  {step.interactive === "security_score" && (
                    <Link href="/education/security">보안 점수 확인</Link>
                  )}
                </div>
              )}

              {/* 네비게이션 버튼 */}
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 24 }}>
                <button onClick={goBack} disabled={currentStep === 0} style={{
                  padding: "10px 24px", borderRadius: 8, cursor: "pointer",
                  border: "1px solid var(--border)", background: "#fff",
                  opacity: currentStep === 0 ? 0.4 : 1,
                }}>
                  이전
                </button>
                <button onClick={advanceStep} disabled={loading} style={{
                  padding: "10px 24px", borderRadius: 8, cursor: "pointer",
                  border: "none", color: "#fff",
                  background: currentStep === selectedCourse.steps.length - 1 ? "var(--success)" : "var(--primary)",
                }}>
                  {loading ? "저장 중..." : currentStep === selectedCourse.steps.length - 1 ? "코스 완료!" : "다음 단계"}
                </button>
              </div>
            </div>

            {/* 완료 상태 */}
            {progress?.status === "completed" && (
              <div className="card" style={{ marginTop: 16, textAlign: "center", background: "#f0fdf4", borderLeft: "4px solid var(--success)" }}>
                <span style={{ fontSize: 32 }}>&#x2705;</span>
                <p style={{ fontWeight: 600, color: "var(--success)", marginTop: 8 }}>이 코스를 완료했습니다!</p>
              </div>
            )}
          </div>
        )}

        {/* 코스 목록 */}
        {!selectedCourse && (
          <div>
            {["beginner", "intermediate", "advanced"].map((level) => {
              const conf = LEVEL_CONFIG[level];
              const levelCourses = grouped[level] || [];
              if (levelCourses.length === 0) return null;
              return (
                <div key={level} style={{ marginBottom: 32 }}>
                  <h2 style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{
                      padding: "4px 12px", borderRadius: 12, fontSize: 14, fontWeight: 600,
                      background: conf.bg, color: conf.color,
                    }}>
                      {conf.label}
                    </span>
                    Level {level === "beginner" ? 1 : level === "intermediate" ? 2 : 3}
                  </h2>
                  <div className="grid grid-2">
                    {levelCourses.map((course) => (
                      <div key={course.course_id} className="card" style={{
                        cursor: "pointer", borderLeft: `4px solid ${conf.color}`,
                      }} onClick={() => selectCourse(course)}>
                        <h3 style={{ marginBottom: 8 }}>{course.title}</h3>
                        <p className="text-secondary" style={{ fontSize: 14, marginBottom: 8 }}>{course.description}</p>
                        <span className="text-secondary" style={{ fontSize: 13 }}>{course.total_steps}단계</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </>
  );
}

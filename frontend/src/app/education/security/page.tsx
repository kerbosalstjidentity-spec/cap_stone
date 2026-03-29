"use client";

import { useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/hooks/useAuth";

const ACTION_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  PASS: { label: "정상 (PASS)", color: "#22c55e", bg: "#f0fdf4" },
  SOFT_REVIEW: { label: "주의 관찰 (SOFT_REVIEW)", color: "#f59e0b", bg: "#fffbeb" },
  REVIEW: { label: "검토 필요 (REVIEW)", color: "#f97316", bg: "#fff7ed" },
  BLOCK: { label: "차단 (BLOCK)", color: "#ef4444", bg: "#fef2f2" },
};

function SecurityContent() {
  const { userId } = useAuth();
  const [tab, setTab] = useState<"quiz" | "simulate">("quiz");

  const [quizQuestions, setQuizQuestions] = useState<any[]>([]);
  const [quizAnswers, setQuizAnswers] = useState<Record<number, string>>({});
  const [quizSubmitted, setQuizSubmitted] = useState(false);
  const [quizLoading, setQuizLoading] = useState(false);

  const [simAmount, setSimAmount] = useState(500000);
  const [simHour, setSimHour] = useState(14);
  const [simForeign, setSimForeign] = useState(false);
  const [simNewMerchant, setSimNewMerchant] = useState(false);
  const [simCategory, setSimCategory] = useState("shopping");
  const [simResult, setSimResult] = useState<any>(null);
  const [simLoading, setSimLoading] = useState(false);

  const [spendingQuiz, setSpendingQuiz] = useState<any[]>([]);
  const [spendingAnswers, setSpendingAnswers] = useState<Record<number, string>>({});
  const [spendingSubmitted, setSpendingSubmitted] = useState(false);
  const [spendingLoading, setSpendingLoading] = useState(false);

  const startFraudQuiz = async () => {
    setQuizLoading(true); setQuizSubmitted(false); setQuizAnswers({});
    try {
      const res = await fetch(`/api/v1/education/quiz/fraud?user_id=${userId}&count=5`, { method: "POST" });
      const data = await res.json();
      setQuizQuestions(data.questions || []);
    } finally { setQuizLoading(false); }
  };

  const fraudScore = quizSubmitted ? quizQuestions.reduce((acc, q, i) => acc + (quizAnswers[i] === q.correct_answer ? 1 : 0), 0) : 0;

  const startSpendingQuiz = async () => {
    setSpendingLoading(true); setSpendingSubmitted(false); setSpendingAnswers({});
    try {
      const res = await fetch(`/api/v1/education/quiz/spending?user_id=${userId}&count=5`, { method: "POST" });
      const data = await res.json();
      setSpendingQuiz(data.questions || []);
    } finally { setSpendingLoading(false); }
  };

  const spendingScore = spendingSubmitted ? spendingQuiz.reduce((acc, q, i) => acc + (spendingAnswers[i] === q.correct_answer ? 1 : 0), 0) : 0;

  const runSimulation = async () => {
    setSimLoading(true);
    try {
      const res = await fetch("/api/v1/education/simulate/fraud", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount: simAmount, hour: simHour, is_foreign_ip: simForeign, category: simCategory, is_new_merchant: simNewMerchant }),
      });
      setSimResult(await res.json());
    } finally { setSimLoading(false); }
  };

  const actionConf = simResult ? ACTION_CONFIG[simResult.final_action] || ACTION_CONFIG.PASS : null;

  return (
    <>
      <NavBar activePath="/education" />
      <main className="container">
        <h1 style={{ marginBottom: 24 }}>보안 교육</h1>

        <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
          {[{ key: "quiz" as const, label: "퀴즈" }, { key: "simulate" as const, label: "사기 시뮬레이터" }].map(({ key, label }) => (
            <button key={key} onClick={() => setTab(key)} style={{
              padding: "10px 24px", borderRadius: 8, cursor: "pointer",
              border: tab === key ? "2px solid var(--primary)" : "1px solid var(--border)",
              background: tab === key ? "#eef2ff" : "#fff",
              color: tab === key ? "var(--primary)" : "var(--text-secondary)",
              fontWeight: tab === key ? 600 : 400, fontSize: 15,
            }}>
              {label}
            </button>
          ))}
        </div>

        {tab === "quiz" && (
          <div className="grid grid-2">
            {/* 사기 탐지 퀴즈 */}
            <div className="card">
              <h3 style={{ marginBottom: 12 }}>사기 탐지 퀴즈</h3>
              <p className="text-secondary" style={{ marginBottom: 16, fontSize: 14 }}>실제 거래 패턴 기반 — 이 거래는 정상일까, 사기일까?</p>
              {quizQuestions.length === 0 && (
                <button onClick={startFraudQuiz} disabled={quizLoading} style={{ padding: "10px 24px", borderRadius: 8, border: "none", background: "var(--primary)", color: "#fff", cursor: "pointer" }}>
                  {quizLoading ? "문제 생성 중..." : "퀴즈 시작"}
                </button>
              )}
              {quizQuestions.map((q: any, i: number) => (
                <div key={i} style={{ padding: "14px 16px", margin: "10px 0", borderRadius: 10, border: "1px solid var(--border)", background: quizSubmitted ? quizAnswers[i] === q.correct_answer ? "#f0fdf4" : "#fef2f2" : "#fff" }}>
                  <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 14 }}>Q{i + 1}. {q.transaction_summary}</div>
                  <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                    {q.options.map((opt: string) => (
                      <button key={opt} onClick={() => !quizSubmitted && setQuizAnswers({ ...quizAnswers, [i]: opt })} disabled={quizSubmitted} style={{
                        flex: 1, padding: "8px", borderRadius: 8, fontSize: 14, cursor: quizSubmitted ? "default" : "pointer",
                        border: quizAnswers[i] === opt ? "2px solid var(--primary)" : "1px solid var(--border)",
                        background: quizSubmitted && opt === q.correct_answer ? "#dcfce7" : quizSubmitted && quizAnswers[i] === opt && opt !== q.correct_answer ? "#fecaca" : quizAnswers[i] === opt ? "#eef2ff" : "#fff",
                        fontWeight: quizAnswers[i] === opt ? 600 : 400,
                      }}>{opt}</button>
                    ))}
                  </div>
                  {quizSubmitted && <div style={{ padding: "8px 12px", borderRadius: 6, fontSize: 13, background: "#f8fafc", lineHeight: 1.6 }}><strong>해설:</strong> {q.explanation}</div>}
                </div>
              ))}
              {quizQuestions.length > 0 && !quizSubmitted && (
                <button onClick={() => setQuizSubmitted(true)} disabled={Object.keys(quizAnswers).length < quizQuestions.length} style={{ width: "100%", marginTop: 12, padding: "10px", borderRadius: 8, border: "none", background: Object.keys(quizAnswers).length < quizQuestions.length ? "#94a3b8" : "var(--primary)", color: "#fff", cursor: "pointer" }}>
                  제출하기
                </button>
              )}
              {quizSubmitted && (
                <div style={{ textAlign: "center", marginTop: 16, padding: 16, borderRadius: 10, background: "#f8fafc" }}>
                  <div style={{ fontSize: 28, fontWeight: 700, color: fraudScore >= 4 ? "var(--success)" : "var(--warning)" }}>{fraudScore}/{quizQuestions.length} 정답</div>
                  <p className="text-secondary" style={{ marginTop: 4 }}>{fraudScore === quizQuestions.length ? "완벽합니다! 보안 전문가 수준이에요!" : fraudScore >= 3 ? "좋습니다! 조금만 더 공부하면 완벽해요." : "사기 패턴에 대해 더 학습이 필요합니다."}</p>
                  <button onClick={startFraudQuiz} style={{ marginTop: 12, padding: "8px 20px", borderRadius: 8, border: "none", background: "var(--primary)", color: "#fff", cursor: "pointer" }}>다시 도전</button>
                </div>
              )}
            </div>

            {/* 소비 습관 퀴즈 */}
            <div className="card">
              <h3 style={{ marginBottom: 12 }}>소비 습관 퀴즈</h3>
              <p className="text-secondary" style={{ marginBottom: 16, fontSize: 14 }}>예산, 저축, 투자, 보안 관련 금융 상식 퀴즈</p>
              {spendingQuiz.length === 0 && (
                <button onClick={startSpendingQuiz} disabled={spendingLoading} style={{ padding: "10px 24px", borderRadius: 8, border: "none", background: "#22c55e", color: "#fff", cursor: "pointer" }}>
                  {spendingLoading ? "문제 생성 중..." : "퀴즈 시작"}
                </button>
              )}
              {spendingQuiz.map((q: any, i: number) => (
                <div key={i} style={{ padding: "14px 16px", margin: "10px 0", borderRadius: 10, border: "1px solid var(--border)", background: spendingSubmitted ? spendingAnswers[i] === q.correct_answer ? "#f0fdf4" : "#fef2f2" : "#fff" }}>
                  <div style={{ fontWeight: 600, marginBottom: 10, fontSize: 14 }}>Q{i + 1}. {q.question}</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {q.options.map((opt: string) => (
                      <button key={opt} onClick={() => !spendingSubmitted && setSpendingAnswers({ ...spendingAnswers, [i]: opt })} disabled={spendingSubmitted} style={{
                        padding: "10px 14px", borderRadius: 8, textAlign: "left", fontSize: 14, cursor: spendingSubmitted ? "default" : "pointer",
                        border: spendingAnswers[i] === opt ? "2px solid var(--primary)" : "1px solid var(--border)",
                        background: spendingSubmitted && opt === q.correct_answer ? "#dcfce7" : spendingSubmitted && spendingAnswers[i] === opt && opt !== q.correct_answer ? "#fecaca" : spendingAnswers[i] === opt ? "#eef2ff" : "#fff",
                        fontWeight: spendingAnswers[i] === opt ? 600 : 400,
                      }}>{opt}</button>
                    ))}
                  </div>
                  {spendingSubmitted && <div style={{ padding: "8px 12px", borderRadius: 6, fontSize: 13, background: "#f8fafc", lineHeight: 1.6, marginTop: 8 }}><strong>해설:</strong> {q.explanation}</div>}
                </div>
              ))}
              {spendingQuiz.length > 0 && !spendingSubmitted && (
                <button onClick={() => setSpendingSubmitted(true)} disabled={Object.keys(spendingAnswers).length < spendingQuiz.length} style={{ width: "100%", marginTop: 12, padding: "10px", borderRadius: 8, border: "none", background: Object.keys(spendingAnswers).length < spendingQuiz.length ? "#94a3b8" : "#22c55e", color: "#fff", cursor: "pointer" }}>제출하기</button>
              )}
              {spendingSubmitted && (
                <div style={{ textAlign: "center", marginTop: 16, padding: 16, borderRadius: 10, background: "#f8fafc" }}>
                  <div style={{ fontSize: 28, fontWeight: 700, color: spendingScore >= 4 ? "var(--success)" : "var(--warning)" }}>{spendingScore}/{spendingQuiz.length} 정답</div>
                  <button onClick={startSpendingQuiz} style={{ marginTop: 12, padding: "8px 20px", borderRadius: 8, border: "none", background: "#22c55e", color: "#fff", cursor: "pointer" }}>다시 도전</button>
                </div>
              )}
            </div>
          </div>
        )}

        {tab === "simulate" && (
          <div className="grid grid-2">
            <div className="card">
              <h3 style={{ marginBottom: 16 }}>사기 시나리오 시뮬레이터</h3>
              <p className="text-secondary" style={{ marginBottom: 20, fontSize: 14 }}>가상 거래 조건을 설정하고, 사기 탐지 시스템이 어떻게 판정하는지 확인하세요.</p>
              <div style={{ marginBottom: 16 }}>
                <label className="text-secondary" style={{ fontSize: 13, display: "block", marginBottom: 4 }}>거래 금액 (원)</label>
                <input type="number" value={simAmount} onChange={(e) => setSimAmount(Number(e.target.value))} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8 }} />
                <input type="range" min={0} max={10000000} step={100000} value={simAmount} onChange={(e) => setSimAmount(Number(e.target.value))} style={{ width: "100%", marginTop: 4 }} />
              </div>
              <div style={{ marginBottom: 16 }}>
                <label className="text-secondary" style={{ fontSize: 13, display: "block", marginBottom: 4 }}>거래 시간 ({simHour}시)</label>
                <input type="range" min={0} max={23} value={simHour} onChange={(e) => setSimHour(Number(e.target.value))} style={{ width: "100%" }} />
              </div>
              <div style={{ marginBottom: 16 }}>
                <label className="text-secondary" style={{ fontSize: 13, display: "block", marginBottom: 4 }}>카테고리</label>
                <select value={simCategory} onChange={(e) => setSimCategory(e.target.value)} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8 }}>
                  {["food", "shopping", "transport", "entertainment", "education", "finance"].map((c) => (
                    <option key={c} value={c}>{({ food: "식비", shopping: "쇼핑", transport: "교통", entertainment: "여가", education: "교육", finance: "금융" } as any)[c]}</option>
                  ))}
                </select>
              </div>
              <div style={{ display: "flex", gap: 20, marginBottom: 20 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                  <input type="checkbox" checked={simForeign} onChange={(e) => setSimForeign(e.target.checked)} />
                  <span style={{ fontSize: 14 }}>해외 IP</span>
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                  <input type="checkbox" checked={simNewMerchant} onChange={(e) => setSimNewMerchant(e.target.checked)} />
                  <span style={{ fontSize: 14 }}>신규 가맹점</span>
                </label>
              </div>
              <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
                <button onClick={() => { setSimAmount(4500); setSimHour(12); setSimForeign(false); setSimNewMerchant(false); }} style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid var(--border)", background: "#fff", cursor: "pointer", fontSize: 12 }}>일반 점심</button>
                <button onClick={() => { setSimAmount(1500000); setSimHour(3); setSimForeign(true); setSimNewMerchant(true); }} style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid var(--danger)", background: "#fef2f2", cursor: "pointer", fontSize: 12, color: "var(--danger)" }}>고위험 시나리오</button>
                <button onClick={() => { setSimAmount(500000); setSimHour(9); setSimForeign(false); setSimNewMerchant(false); setSimCategory("finance"); }} style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid var(--border)", background: "#fff", cursor: "pointer", fontSize: 12 }}>적금 이체</button>
              </div>
              <button onClick={runSimulation} disabled={simLoading} style={{ width: "100%", padding: "12px", borderRadius: 8, border: "none", background: "var(--primary)", color: "#fff", cursor: "pointer", fontSize: 15 }}>
                {simLoading ? "분석 중..." : "판정 시뮬레이션"}
              </button>
            </div>

            {simResult && actionConf ? (
              <div className="card">
                <h3 style={{ marginBottom: 16 }}>판정 결과</h3>
                <div style={{ textAlign: "center", padding: 24, borderRadius: 12, background: actionConf.bg, marginBottom: 20 }}>
                  <div style={{ fontSize: 28, fontWeight: 700, color: actionConf.color }}>{actionConf.label}</div>
                  <p style={{ marginTop: 8, fontSize: 14, color: "var(--text-secondary)" }}>{simResult.risk_explanation}</p>
                </div>
                <h4 style={{ marginBottom: 12 }}>감지된 규칙</h4>
                {simResult.rules_triggered.map((r: any, i: number) => {
                  const rConf = ACTION_CONFIG[r.action] || ACTION_CONFIG.PASS;
                  return (
                    <div key={i} style={{ padding: "12px 16px", margin: "8px 0", borderRadius: 8, borderLeft: `3px solid ${rConf.color}`, background: rConf.bg }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ fontWeight: 600, fontSize: 14 }}>{r.rule}</span>
                        <span style={{ fontSize: 12, color: rConf.color, fontWeight: 600 }}>{r.action}</span>
                      </div>
                      <div className="text-secondary" style={{ fontSize: 13 }}>{r.reason}</div>
                    </div>
                  );
                })}
                <h4 style={{ marginTop: 20, marginBottom: 12 }}>예방 팁</h4>
                {simResult.prevention_tips.map((tip: string, i: number) => (
                  <div key={i} style={{ padding: "10px 14px", margin: "6px 0", borderRadius: 8, background: "#f0fdf4", borderLeft: "3px solid var(--success)", fontSize: 14 }}>{tip}</div>
                ))}
              </div>
            ) : (
              <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
                <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>🛡️</div>
                <p className="text-secondary" style={{ textAlign: "center" }}>거래 조건을 설정하고<br />시뮬레이션을 실행하세요</p>
              </div>
            )}
          </div>
        )}
      </main>
    </>
  );
}

export default function SecurityPage() {
  return (
    <AuthGuard>
      <SecurityContent />
    </AuthGuard>
  );
}

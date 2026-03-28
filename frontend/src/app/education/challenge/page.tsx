"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const BADGE_ICONS: Record<string, string> = {
  coffee: "\u2615", shield: "\uD83D\uDEE1\uFE0F", star: "\u2B50",
  lock: "\uD83D\uDD12", refresh: "\uD83D\uDD04",
};

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  active: { label: "진행 중", color: "#3b82f6", bg: "#eff6ff" },
  completed: { label: "완료", color: "#22c55e", bg: "#f0fdf4" },
  failed: { label: "실패", color: "#ef4444", bg: "#fef2f2" },
};

export default function ChallengePage() {
  const [userId, setUserId] = useState("demo_user");
  const [challenges, setChallenges] = useState<any[]>([]);
  const [userChallenges, setUserChallenges] = useState<any[]>([]);
  const [badges, setBadges] = useState<any[]>([]);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/v1/education/challenges").then((r) => r.json()).then((d) => setChallenges(d.challenges || []));
  }, []);

  const fetchUserData = async () => {
    setLoading(true);
    const [ch, bg, lb] = await Promise.allSettled([
      fetch(`/api/v1/education/user-challenges/${userId}`).then((r) => r.json()),
      fetch(`/api/v1/education/badges/${userId}`).then((r) => r.json()),
      fetch("/api/v1/education/leaderboard?top_n=10").then((r) => r.json()),
    ]);
    if (ch.status === "fulfilled") setUserChallenges(ch.value.challenges || []);
    if (bg.status === "fulfilled") setBadges(bg.value.badges || []);
    if (lb.status === "fulfilled") setLeaderboard(lb.value.leaderboard || []);
    setLoading(false);
  };

  const enrollChallenge = async (challengeId: string) => {
    await fetch(`/api/v1/education/challenge/${challengeId}/enroll?user_id=${userId}`, { method: "POST" });
    await fetchUserData();
  };

  const isEnrolled = (challengeId: string) => userChallenges.some((c) => c.challenge_id === challengeId);

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
          <h1>챌린지 & 배지</h1>
          <input
            value={userId} onChange={(e) => setUserId(e.target.value)}
            style={{ padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8 }}
          />
          <button onClick={fetchUserData} disabled={loading} style={{
            padding: "8px 20px", background: "var(--primary)", color: "#fff",
            border: "none", borderRadius: 8, cursor: "pointer",
          }}>
            {loading ? "로딩..." : "내 현황 조회"}
          </button>
        </div>

        <div className="grid grid-2">
          {/* 참여 중인 챌린지 */}
          <div className="card">
            <h3 style={{ marginBottom: 16 }}>내 챌린지</h3>
            {userChallenges.length > 0 ? (
              userChallenges.map((uc: any) => {
                const status = STATUS_CONFIG[uc.status] || STATUS_CONFIG.active;
                const ch = challenges.find((c) => c.challenge_id === uc.challenge_id);
                return (
                  <div key={uc.challenge_id} style={{
                    padding: "14px 16px", margin: "8px 0", borderRadius: 10,
                    border: "1px solid var(--border)", background: "#fff",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <span style={{ fontWeight: 600 }}>{ch?.name || uc.challenge_id}</span>
                      <span style={{
                        padding: "3px 10px", borderRadius: 12, fontSize: 12, fontWeight: 600,
                        background: status.bg, color: status.color,
                      }}>
                        {status.label}
                      </span>
                    </div>
                    <div style={{ height: 8, background: "#e2e8f0", borderRadius: 4, overflow: "hidden", marginBottom: 6 }}>
                      <div style={{
                        height: "100%", borderRadius: 4,
                        background: status.color,
                        width: `${uc.progress_pct}%`,
                        transition: "width 0.3s",
                      }} />
                    </div>
                    <div className="text-secondary" style={{ fontSize: 12 }}>
                      진행률 {uc.progress_pct.toFixed(0)}%
                    </div>
                  </div>
                );
              })
            ) : (
              <p className="text-secondary" style={{ textAlign: "center", padding: 24 }}>
                참여 중인 챌린지가 없습니다.<br />아래에서 챌린지를 선택하세요!
              </p>
            )}
          </div>

          {/* 배지 컬렉션 */}
          <div className="card">
            <h3 style={{ marginBottom: 16 }}>
              배지 컬렉션
              <span className="badge badge-primary" style={{ marginLeft: 8 }}>{badges.length}개</span>
            </h3>
            {badges.length > 0 ? (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
                {badges.map((b: any, i: number) => (
                  <div key={i} style={{
                    textAlign: "center", padding: "16px", borderRadius: 12,
                    border: "1px solid var(--border)", minWidth: 100,
                  }}>
                    <div style={{ fontSize: 32 }}>{BADGE_ICONS[b.badge_icon] || "\uD83C\uDFC5"}</div>
                    <div style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>{b.badge_name}</div>
                    <div className="text-secondary" style={{ fontSize: 11, marginTop: 2 }}>{b.description}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ textAlign: "center", padding: 32 }}>
                <div style={{ fontSize: 48, opacity: 0.3 }}>{"\uD83C\uDFC5"}</div>
                <p className="text-secondary" style={{ marginTop: 8 }}>챌린지를 완료하면 배지를 획득할 수 있습니다!</p>
              </div>
            )}
          </div>
        </div>

        {/* 챌린지 목록 */}
        <h2 style={{ marginTop: 32, marginBottom: 16 }}>챌린지 도전하기</h2>
        <div className="grid grid-3">
          {challenges.map((ch: any) => {
            const enrolled = isEnrolled(ch.challenge_id);
            return (
              <div key={ch.challenge_id} className="card" style={{
                borderTop: enrolled ? "3px solid var(--success)" : "3px solid var(--primary)",
              }}>
                <div style={{ fontSize: 28, marginBottom: 8 }}>{BADGE_ICONS[ch.badge_icon] || "\uD83C\uDFC5"}</div>
                <h3 style={{ marginBottom: 4 }}>{ch.name}</h3>
                <p className="text-secondary" style={{ fontSize: 14, marginBottom: 8 }}>{ch.description}</p>
                <div className="text-secondary" style={{ fontSize: 13, marginBottom: 12 }}>
                  {ch.duration_days}일 | 보상: {ch.badge_name}
                </div>
                <button onClick={() => !enrolled && enrollChallenge(ch.challenge_id)}
                  disabled={enrolled}
                  style={{
                    width: "100%", padding: "10px", borderRadius: 8, cursor: enrolled ? "default" : "pointer",
                    border: "none", color: "#fff", fontSize: 14,
                    background: enrolled ? "var(--success)" : "var(--primary)",
                  }}>
                  {enrolled ? "참여 중" : "도전하기"}
                </button>
              </div>
            );
          })}
        </div>

        {/* 리더보드 */}
        {leaderboard.length > 0 && (
          <div style={{ marginTop: 32 }}>
            <h2 style={{ marginBottom: 16 }}>리더보드</h2>
            <div className="card">
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid var(--border)" }}>
                    <th style={{ padding: "10px 12px", textAlign: "left", fontSize: 13 }}>순위</th>
                    <th style={{ padding: "10px 12px", textAlign: "left", fontSize: 13 }}>사용자</th>
                    <th style={{ padding: "10px 12px", textAlign: "center", fontSize: 13 }}>배���</th>
                    <th style={{ padding: "10px 12px", textAlign: "center", fontSize: 13 }}>챌린지</th>
                    <th style={{ padding: "10px 12px", textAlign: "center", fontSize: 13 }}>퀴즈 평균</th>
                    <th style={{ padding: "10px 12px", textAlign: "right", fontSize: 13 }}>포인트</th>
                  </tr>
                </thead>
                <tbody>
                  {leaderboard.map((e: any) => (
                    <tr key={e.rank} style={{
                      borderBottom: "1px solid var(--border)",
                      background: e.user_id === userId ? "#eef2ff" : "transparent",
                    }}>
                      <td style={{ padding: "10px 12px", fontWeight: 600 }}>
                        {e.rank <= 3 ? ["\uD83E\uDD47", "\uD83E\uDD48", "\uD83E\uDD49"][e.rank - 1] : e.rank}
                      </td>
                      <td style={{ padding: "10px 12px" }}>{e.user_id}</td>
                      <td style={{ padding: "10px 12px", textAlign: "center" }}>{e.badge_count}</td>
                      <td style={{ padding: "10px 12px", textAlign: "center" }}>{e.challenge_completed}</td>
                      <td style={{ padding: "10px 12px", textAlign: "center" }}>{e.quiz_score_avg}%</td>
                      <td style={{ padding: "10px 12px", textAlign: "right", fontWeight: 600, color: "var(--primary)" }}>
                        {e.total_points}P
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </>
  );
}

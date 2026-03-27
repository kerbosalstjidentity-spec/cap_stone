"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface CategoryBreakdown {
  category: string;
  total_amount: number;
  tx_count: number;
  avg_amount: number;
  pct_of_total: number;
}

interface Profile {
  user_id: string;
  total_tx_count: number;
  total_amount: number;
  avg_amount: number;
  max_amount: number;
  peak_hour: number;
  top_category: string;
  category_breakdown: CategoryBreakdown[];
}

const CATEGORY_LABELS: Record<string, string> = {
  food: "식비",
  shopping: "쇼핑",
  transport: "교통",
  entertainment: "여가",
  education: "교육",
  healthcare: "의료",
  housing: "주거",
  utilities: "공과금",
  finance: "금융",
  travel: "여행",
  other: "기타",
};

const CATEGORY_COLORS: Record<string, string> = {
  food: "#ef4444",
  shopping: "#f59e0b",
  transport: "#3b82f6",
  entertainment: "#8b5cf6",
  education: "#22c55e",
  healthcare: "#06b6d4",
  housing: "#ec4899",
  utilities: "#64748b",
  finance: "#14b8a6",
  travel: "#f97316",
  other: "#94a3b8",
};

function formatKRW(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}만원`;
  return `${n.toLocaleString()}원`;
}

export default function DashboardPage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [userId, setUserId] = useState("demo_user");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchProfile = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`/api/v1/profile/${userId}`);
      if (!res.ok) throw new Error("프로필을 불러올 수 없습니다");
      setProfile(await res.json());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProfile();
  }, []);

  return (
    <>
      <nav>
        <div className="container">
          <h2>ConsumePattern</h2>
          <Link href="/dashboard" className="active">대시보드</Link>
          <Link href="/analysis">패턴 분석</Link>
          <Link href="/strategy">전략 제안</Link>
        </div>
      </nav>
      <main className="container">
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
          <h1>소비 대시보드</h1>
          <input
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="User ID"
            style={{ padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8 }}
          />
          <button onClick={fetchProfile} style={{
            padding: "8px 20px", background: "var(--primary)", color: "#fff",
            border: "none", borderRadius: 8, cursor: "pointer",
          }}>
            조회
          </button>
        </div>

        {loading && <p>로딩 중...</p>}
        {error && <p className="text-danger">{error}</p>}

        {profile && (
          <>
            <div className="grid grid-4" style={{ marginBottom: 24 }}>
              <div className="card">
                <div className="stat-label">총 지출</div>
                <div className="stat-value">{formatKRW(profile.total_amount)}</div>
              </div>
              <div className="card">
                <div className="stat-label">거래 건수</div>
                <div className="stat-value">{profile.total_tx_count}건</div>
              </div>
              <div className="card">
                <div className="stat-label">건당 평균</div>
                <div className="stat-value">{formatKRW(profile.avg_amount)}</div>
              </div>
              <div className="card">
                <div className="stat-label">최대 지출</div>
                <div className="stat-value">{formatKRW(profile.max_amount)}</div>
              </div>
            </div>

            <div className="grid grid-2">
              <div className="card">
                <h3 style={{ marginBottom: 16 }}>카테고리별 지출</h3>
                {profile.category_breakdown.map((cat) => (
                  <div key={cat.category} style={{ marginBottom: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                      <span>{CATEGORY_LABELS[cat.category] || cat.category}</span>
                      <span>{formatKRW(cat.total_amount)} ({(cat.pct_of_total * 100).toFixed(1)}%)</span>
                    </div>
                    <div className="progress-bar">
                      <div
                        className="fill"
                        style={{
                          width: `${cat.pct_of_total * 100}%`,
                          background: CATEGORY_COLORS[cat.category] || "#94a3b8",
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              <div className="card">
                <h3 style={{ marginBottom: 16 }}>소비 요약</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <div>
                    <span className="text-secondary">주 소비 카테고리: </span>
                    <span className="badge badge-primary">
                      {CATEGORY_LABELS[profile.top_category] || profile.top_category}
                    </span>
                  </div>
                  <div>
                    <span className="text-secondary">활동 피크 시간: </span>
                    <span className="badge badge-primary">{profile.peak_hour}시</span>
                  </div>
                  <div>
                    <span className="text-secondary">카테고리 수: </span>
                    <span className="badge badge-primary">{profile.category_breakdown.length}개</span>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </main>
    </>
  );
}

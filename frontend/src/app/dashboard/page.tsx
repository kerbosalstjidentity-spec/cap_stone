"use client";

import { useEffect, useState } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from "recharts";
import AuthGuard from "@/components/AuthGuard";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/hooks/useAuth";

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

interface TrendPoint {
  period: string;
  total_amount: number;
  category_amounts: Record<string, number>;
}

const CATEGORY_LABELS: Record<string, string> = {
  food: "식비", shopping: "쇼핑", transport: "교통", entertainment: "여가",
  education: "교육", healthcare: "의료", housing: "주거", utilities: "공과금",
  finance: "금융", travel: "여행", other: "기타",
};

const CATEGORY_COLORS: Record<string, string> = {
  food: "#ef4444", shopping: "#f59e0b", transport: "#3b82f6",
  entertainment: "#8b5cf6", education: "#22c55e", healthcare: "#06b6d4",
  housing: "#ec4899", utilities: "#64748b", finance: "#14b8a6",
  travel: "#f97316", other: "#94a3b8",
};

function formatKRW(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}만원`;
  return `${n.toLocaleString()}원`;
}

function DashboardContent() {
  const { userId } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [seeding, setSeeding] = useState(false);

  const fetchProfile = async () => {
    if (!userId) return;
    setLoading(true);
    setError("");
    try {
      const [profRes, trendRes] = await Promise.allSettled([
        fetch(`/api/v1/profile/${userId}`).then((r) => {
          if (!r.ok) throw new Error("not found");
          return r.json();
        }),
        fetch(`/api/v1/profile/${userId}/trend`).then((r) => (r.ok ? r.json() : null)),
      ]);
      if (profRes.status === "fulfilled") setProfile(profRes.value);
      else setError("소비 데이터가 없습니다. 아래 버튼으로 데모 데이터를 생성해보세요.");
      if (trendRes.status === "fulfilled" && trendRes.value)
        setTrend(trendRes.value.trend || []);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const seedDemo = async () => {
    if (!userId) return;
    setSeeding(true);
    try {
      const res = await fetch(`/api/v1/seed/demo/${userId}?months=3&tx_per_month=40`, {
        method: "POST",
      });
      if (res.ok) await fetchProfile();
    } finally {
      setSeeding(false);
    }
  };

  useEffect(() => {
    if (userId) fetchProfile();
  }, [userId]);

  const pieData =
    profile?.category_breakdown.map((cat) => ({
      name: CATEGORY_LABELS[cat.category] || cat.category,
      value: cat.total_amount,
      color: CATEGORY_COLORS[cat.category] || "#94a3b8",
    })) || [];

  const barData = trend.map((t) => ({ period: t.period, total: t.total_amount }));

  return (
    <>
      <NavBar activePath="/dashboard" />
      <main className="container">
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
          <h1>소비 대시보드</h1>
          <button
            onClick={fetchProfile}
            style={{
              padding: "8px 20px", background: "var(--primary)", color: "#fff",
              border: "none", borderRadius: 8, cursor: "pointer",
            }}
          >
            새로고침
          </button>
          <button
            onClick={seedDemo}
            disabled={seeding}
            style={{
              padding: "8px 20px", background: "#22c55e", color: "#fff",
              border: "none", borderRadius: 8, cursor: "pointer", opacity: seeding ? 0.6 : 1,
            }}
          >
            {seeding ? "생성 중..." : "데모 데이터 생성"}
          </button>
        </div>

        {loading && <p>로딩 중...</p>}

        {error && (
          <div className="card" style={{ textAlign: "center", padding: 40 }}>
            <p className="text-secondary" style={{ marginBottom: 16 }}>{error}</p>
            <button
              onClick={seedDemo}
              disabled={seeding}
              style={{
                padding: "12px 32px", background: "var(--primary)", color: "#fff",
                border: "none", borderRadius: 8, cursor: "pointer", fontSize: 16,
              }}
            >
              {seeding ? "생성 중..." : "3개월 데모 데이터 자동 생성"}
            </button>
          </div>
        )}

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
                <h3 style={{ marginBottom: 16 }}>카테고리별 지출 분포</h3>
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={60} outerRadius={110} paddingAngle={2} dataKey="value">
                      {pieData.map((entry, idx) => <Cell key={idx} fill={entry.color} />)}
                    </Pie>
                    <Tooltip formatter={(value: number) => formatKRW(value)} contentStyle={{ borderRadius: 8 }} />
                  </PieChart>
                </ResponsiveContainer>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
                  {pieData.map((d, i) => (
                    <span key={i} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 13 }}>
                      <span style={{ width: 10, height: 10, borderRadius: "50%", background: d.color, display: "inline-block" }} />
                      {d.name}
                    </span>
                  ))}
                </div>
              </div>

              <div className="card">
                <h3 style={{ marginBottom: 16 }}>카테고리별 지출</h3>
                {profile.category_breakdown.map((cat) => (
                  <div key={cat.category} style={{ marginBottom: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                      <span>{CATEGORY_LABELS[cat.category] || cat.category}</span>
                      <span>{formatKRW(cat.total_amount)} ({(cat.pct_of_total * 100).toFixed(1)}%)</span>
                    </div>
                    <div className="progress-bar">
                      <div className="fill" style={{ width: `${cat.pct_of_total * 100}%`, background: CATEGORY_COLORS[cat.category] || "#94a3b8" }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {barData.length > 0 && (
              <div className="card" style={{ marginTop: 24 }}>
                <h3 style={{ marginBottom: 16 }}>월별 지출 추이</h3>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={barData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="period" tick={{ fontSize: 13 }} />
                    <YAxis tickFormatter={(v) => `${(v / 10000).toFixed(0)}만`} tick={{ fontSize: 13 }} />
                    <Tooltip formatter={(value: number) => formatKRW(value)} />
                    <Bar dataKey="total" fill="#4f46e5" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            <div className="card" style={{ marginTop: 24 }}>
              <h3 style={{ marginBottom: 16 }}>소비 요약</h3>
              <div style={{ display: "flex", gap: 32, flexWrap: "wrap" }}>
                <div>
                  <span className="text-secondary">주 소비 카테고리: </span>
                  <span className="badge badge-primary">{CATEGORY_LABELS[profile.top_category] || profile.top_category}</span>
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
          </>
        )}
      </main>
    </>
  );
}

export default function DashboardPage() {
  return (
    <AuthGuard>
      <DashboardContent />
    </AuthGuard>
  );
}

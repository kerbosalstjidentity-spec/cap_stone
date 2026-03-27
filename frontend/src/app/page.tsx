"use client";

import Link from "next/link";

export default function Home() {
  return (
    <>
      <nav>
        <div className="container">
          <h2>ConsumePattern</h2>
          <Link href="/dashboard">대시보드</Link>
          <Link href="/analysis">패턴 분석</Link>
          <Link href="/strategy">전략 제안</Link>
        </div>
      </nav>
      <main className="container">
        <div style={{ textAlign: "center", padding: "80px 0" }}>
          <h1 style={{ marginBottom: 16 }}>AI 기반 지능형 소비 패턴 분석</h1>
          <p className="text-secondary" style={{ fontSize: 18, marginBottom: 40 }}>
            이전 데이터와의 비교 분석을 통해 지출 관리의 효율성을 극대화하고,
            <br />
            사용자의 재무 목표에 맞춘 합리적인 소비 가이드라인을 제시합니다.
          </p>
          <div className="grid grid-3" style={{ maxWidth: 800, margin: "0 auto" }}>
            <Link href="/dashboard" style={{ textDecoration: "none" }}>
              <div className="card" style={{ cursor: "pointer" }}>
                <h3>대시보드</h3>
                <p className="text-secondary" style={{ marginTop: 8 }}>
                  소비 현황 한눈에 보기
                </p>
              </div>
            </Link>
            <Link href="/analysis" style={{ textDecoration: "none" }}>
              <div className="card" style={{ cursor: "pointer" }}>
                <h3>패턴 분석</h3>
                <p className="text-secondary" style={{ marginTop: 8 }}>
                  K-Means, IF, LSTM 분석
                </p>
              </div>
            </Link>
            <Link href="/strategy" style={{ textDecoration: "none" }}>
              <div className="card" style={{ cursor: "pointer" }}>
                <h3>전략 제안</h3>
                <p className="text-secondary" style={{ marginTop: 8 }}>
                  맞춤형 소비 전략
                </p>
              </div>
            </Link>
          </div>
        </div>
      </main>
    </>
  );
}

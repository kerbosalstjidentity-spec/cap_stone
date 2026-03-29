"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type UserProfile = {
  user_id: string;
  email: string | null;
  nickname: string;
  totp_enabled: boolean;
  edu_level: string;
};

type StepUpHistory = {
  method: string;
  verified: boolean;
  risk_score: number;
  created_at: string;
};

type FidoCredential = {
  id: number;
  credential_id_prefix: string;
  name: string;
  device_type: string;
  last_used_at: string | null;
  created_at: string;
};

export default function SecurityPage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [history, setHistory] = useState<StepUpHistory[]>([]);
  const [fidoCreds, setFidoCreds] = useState<FidoCredential[]>([]);
  const [tab, setTab] = useState<"overview" | "totp" | "fido" | "history">("overview");
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);

  // TOTP 설정 상태
  const [totpSetup, setTotpSetup] = useState<{ secret: string; qr_uri: string } | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [totpMsg, setTotpMsg] = useState("");

  // 비밀번호 변경 상태
  const [pwForm, setPwForm] = useState({ current: "", next: "" });
  const [pwMsg, setPwMsg] = useState("");

  useEffect(() => {
    const t = localStorage.getItem("access_token");
    setToken(t);
    if (!t) { setLoading(false); return; }

    const headers = { Authorization: `Bearer ${t}` };

    Promise.all([
      fetch("/api/v1/auth/me", { headers }).then(r => r.ok ? r.json() : null),
      fetch("/api/v1/auth/stepup/history", { headers }).then(r => r.ok ? r.json() : { history: [] }),
      fetch("/api/v1/auth/fido/credentials", { headers }).then(r => r.ok ? r.json() : []),
    ]).then(([prof, hist, creds]) => {
      setProfile(prof);
      setHistory(hist?.history ?? []);
      setFidoCreds(Array.isArray(creds) ? creds : []);
    }).finally(() => setLoading(false));
  }, []);

  async function startTotpSetup() {
    const res = await fetch("/api/v1/auth/me/totp/setup", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) setTotpSetup(await res.json());
  }

  async function verifyTotp() {
    const res = await fetch("/api/v1/auth/me/totp/verify", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ code: totpCode }),
    });
    const data = await res.json();
    if (res.ok) {
      setTotpMsg("TOTP 2FA가 활성화되었습니다!");
      setProfile(p => p ? { ...p, totp_enabled: true } : p);
      setTotpSetup(null);
    } else {
      setTotpMsg(data.detail || "코드가 올바르지 않습니다.");
    }
  }

  async function disableTotp() {
    const code = prompt("현재 OTP 코드를 입력하여 TOTP를 비활성화합니다:");
    if (!code) return;
    const res = await fetch("/api/v1/auth/me/totp/disable", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    if (res.ok) {
      setTotpMsg("TOTP가 비활성화되었습니다.");
      setProfile(p => p ? { ...p, totp_enabled: false } : p);
    }
  }

  async function changePassword() {
    const res = await fetch("/api/v1/auth/me/change-password", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: pwForm.current, new_password: pwForm.next }),
    });
    const data = await res.json();
    setPwMsg(res.ok ? "비밀번호가 변경되었습니다." : (data.detail || "실패했습니다."));
    if (res.ok) setPwForm({ current: "", next: "" });
  }

  async function deleteCredential(id: number) {
    if (!confirm("이 인증 장치를 삭제하시겠습니까?")) return;
    await fetch(`/api/v1/auth/fido/credentials/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    setFidoCreds(creds => creds.filter(c => c.id !== id));
  }

  if (!token) {
    return (
      <>
        <nav><div className="container"><h2>ConsumePattern</h2><Link href="/">홈</Link></div></nav>
        <main className="container" style={{ paddingTop: 80, textAlign: "center" }}>
          <div className="card" style={{ maxWidth: 400, margin: "0 auto" }}>
            <h3>로그인이 필요합니다</h3>
            <p className="text-secondary" style={{ margin: "12px 0 20px" }}>보안 설정을 관리하려면 먼저 로그인하세요.</p>
            <Link href="/auth/login" style={{ color: "#6366f1", fontWeight: 600 }}>로그인하러 가기 →</Link>
          </div>
        </main>
      </>
    );
  }

  const tabStyle = (t: string) => ({
    padding: "8px 16px", borderRadius: 6, cursor: "pointer", fontWeight: 500,
    background: tab === t ? "#6366f1" : "transparent",
    color: tab === t ? "#fff" : "#6b7280",
    border: "none",
  } as React.CSSProperties);

  const securityScore = profile ? (
    (profile.totp_enabled ? 40 : 0) +
    (fidoCreds.length > 0 ? 40 : 0) +
    20
  ) : 20;

  const scoreColor = securityScore >= 80 ? "#10b981" : securityScore >= 50 ? "#f59e0b" : "#ef4444";

  return (
    <>
      <nav>
        <div className="container">
          <h2>ConsumePattern</h2>
          <Link href="/dashboard">대시보드</Link>
          <Link href="/education">교육</Link>
          <Link href="/security" style={{ fontWeight: 700 }}>보안</Link>
        </div>
      </nav>
      <main className="container" style={{ paddingTop: 32 }}>
        <h1 style={{ marginBottom: 4 }}>계정 보안 설정</h1>
        <p className="text-secondary" style={{ marginBottom: 28 }}>
          금융 정보를 안전하게 보호하기 위한 인증 수단을 관리합니다.
        </p>

        {loading ? (
          <p>로딩 중...</p>
        ) : (
          <div className="grid" style={{ gridTemplateColumns: "280px 1fr", gap: 24 }}>
            {/* 사이드바 */}
            <div>
              {/* 보안 점수 카드 */}
              <div className="card" style={{ marginBottom: 16 }}>
                <h4 style={{ marginBottom: 12 }}>내 보안 점수</h4>
                <div style={{ textAlign: "center", padding: "8px 0" }}>
                  <div style={{
                    width: 80, height: 80, borderRadius: "50%",
                    border: `6px solid ${scoreColor}`,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    margin: "0 auto 8px",
                  }}>
                    <span style={{ fontSize: 22, fontWeight: 700, color: scoreColor }}>{securityScore}</span>
                  </div>
                  <p style={{ fontSize: 13, color: "#6b7280" }}>
                    {securityScore >= 80 ? "우수" : securityScore >= 50 ? "보통" : "취약"}
                  </p>
                </div>
                <div style={{ borderTop: "1px solid #f3f4f6", paddingTop: 12, marginTop: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                    <span>기본 로그인</span>
                    <span style={{ color: "#10b981" }}>✓ +20</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                    <span>TOTP 2FA</span>
                    <span style={{ color: profile?.totp_enabled ? "#10b981" : "#9ca3af" }}>
                      {profile?.totp_enabled ? "✓ +40" : "○ +0"}
                    </span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                    <span>FIDO2 생체인증</span>
                    <span style={{ color: fidoCreds.length > 0 ? "#10b981" : "#9ca3af" }}>
                      {fidoCreds.length > 0 ? "✓ +40" : "○ +0"}
                    </span>
                  </div>
                </div>
              </div>

              {/* 탭 버튼 */}
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {[
                  { key: "overview", label: "개요" },
                  { key: "totp", label: "TOTP 2단계 인증" },
                  { key: "fido", label: "FIDO2 생체인증" },
                  { key: "history", label: "보안 이벤트 내역" },
                ].map(({ key, label }) => (
                  <button key={key} style={tabStyle(key)} onClick={() => setTab(key as typeof tab)}>
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* 메인 컨텐츠 */}
            <div>
              {/* 개요 탭 */}
              {tab === "overview" && (
                <div>
                  <div className="card" style={{ marginBottom: 16 }}>
                    <h3 style={{ marginBottom: 16 }}>계정 정보</h3>
                    {profile && (
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                        <div>
                          <p style={{ fontSize: 12, color: "#9ca3af", marginBottom: 4 }}>이메일</p>
                          <p style={{ fontWeight: 500 }}>{profile.email}</p>
                        </div>
                        <div>
                          <p style={{ fontSize: 12, color: "#9ca3af", marginBottom: 4 }}>닉네임</p>
                          <p style={{ fontWeight: 500 }}>{profile.nickname}</p>
                        </div>
                        <div>
                          <p style={{ fontSize: 12, color: "#9ca3af", marginBottom: 4 }}>사용자 ID</p>
                          <p style={{ fontWeight: 500, fontSize: 13 }}>{profile.user_id}</p>
                        </div>
                        <div>
                          <p style={{ fontSize: 12, color: "#9ca3af", marginBottom: 4 }}>교육 레벨</p>
                          <p style={{ fontWeight: 500 }}>{profile.edu_level}</p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 비밀번호 변경 */}
                  <div className="card">
                    <h3 style={{ marginBottom: 16 }}>비밀번호 변경</h3>
                    {pwMsg && (
                      <div style={{
                        background: pwMsg.includes("변경") ? "#f0fdf4" : "#fef2f2",
                        border: `1px solid ${pwMsg.includes("변경") ? "#86efac" : "#fca5a5"}`,
                        borderRadius: 8, padding: "10px 14px", marginBottom: 14, fontSize: 14,
                        color: pwMsg.includes("변경") ? "#16a34a" : "#dc2626",
                      }}>
                        {pwMsg}
                      </div>
                    )}
                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                      <input
                        type="password"
                        placeholder="현재 비밀번호"
                        value={pwForm.current}
                        onChange={e => setPwForm(f => ({ ...f, current: e.target.value }))}
                        style={{ padding: "10px 14px", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 14 }}
                      />
                      <input
                        type="password"
                        placeholder="새 비밀번호 (8자 이상)"
                        value={pwForm.next}
                        onChange={e => setPwForm(f => ({ ...f, next: e.target.value }))}
                        style={{ padding: "10px 14px", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 14 }}
                      />
                      <button
                        onClick={changePassword}
                        style={{
                          padding: "10px", background: "#374151", color: "#fff",
                          border: "none", borderRadius: 8, fontWeight: 600, cursor: "pointer",
                        }}
                      >
                        비밀번호 변경
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* TOTP 탭 */}
              {tab === "totp" && (
                <div className="card">
                  <h3 style={{ marginBottom: 8 }}>TOTP 2단계 인증</h3>
                  <p className="text-secondary" style={{ marginBottom: 20 }}>
                    Google Authenticator 또는 Authy 앱으로 6자리 일회용 코드를 생성해 추가 보안을 설정합니다.
                  </p>

                  {profile?.totp_enabled ? (
                    <div>
                      <div style={{
                        background: "#f0fdf4", border: "1px solid #86efac",
                        borderRadius: 8, padding: 16, marginBottom: 20,
                      }}>
                        <p style={{ color: "#16a34a", fontWeight: 600 }}>✓ TOTP 2FA가 활성화되어 있습니다</p>
                        <p style={{ color: "#15803d", fontSize: 13, marginTop: 4 }}>
                          로그인 시 OTP 앱의 6자리 코드가 추가로 요구됩니다.
                        </p>
                      </div>
                      {totpMsg && <p style={{ color: "#6b7280", marginBottom: 12 }}>{totpMsg}</p>}
                      <button
                        onClick={disableTotp}
                        style={{
                          padding: "10px 20px", background: "#ef4444", color: "#fff",
                          border: "none", borderRadius: 8, fontWeight: 600, cursor: "pointer",
                        }}
                      >
                        TOTP 비활성화
                      </button>
                    </div>
                  ) : (
                    <div>
                      {!totpSetup ? (
                        <button
                          onClick={startTotpSetup}
                          style={{
                            padding: "12px 24px", background: "#6366f1", color: "#fff",
                            border: "none", borderRadius: 8, fontWeight: 600, cursor: "pointer",
                          }}
                        >
                          TOTP 설정 시작
                        </button>
                      ) : (
                        <div>
                          <div style={{ background: "#f8fafc", borderRadius: 8, padding: 16, marginBottom: 16 }}>
                            <p style={{ fontWeight: 500, marginBottom: 8 }}>1. OTP 앱에서 아래 키를 수동 입력하거나</p>
                            <p style={{ fontWeight: 500, marginBottom: 12 }}>2. 아래 URI를 QR 코드로 변환해 스캔하세요</p>
                            <div style={{
                              background: "#1e293b", color: "#e2e8f0", padding: 12, borderRadius: 6,
                              fontFamily: "monospace", fontSize: 13, wordBreak: "break-all", marginBottom: 8,
                            }}>
                              Secret: {totpSetup.secret}
                            </div>
                            <details style={{ marginTop: 8 }}>
                              <summary style={{ cursor: "pointer", fontSize: 13, color: "#6b7280" }}>QR URI 보기</summary>
                              <div style={{
                                background: "#f1f5f9", padding: 10, borderRadius: 6, marginTop: 6,
                                fontFamily: "monospace", fontSize: 11, wordBreak: "break-all",
                              }}>
                                {totpSetup.qr_uri}
                              </div>
                            </details>
                          </div>
                          <p style={{ fontWeight: 500, marginBottom: 8 }}>OTP 앱의 6자리 코드 입력:</p>
                          <div style={{ display: "flex", gap: 8 }}>
                            <input
                              type="text"
                              placeholder="123456"
                              value={totpCode}
                              onChange={e => setTotpCode(e.target.value)}
                              maxLength={6}
                              style={{ flex: 1, padding: "10px 14px", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 16, letterSpacing: 4 }}
                            />
                            <button
                              onClick={verifyTotp}
                              style={{
                                padding: "10px 20px", background: "#10b981", color: "#fff",
                                border: "none", borderRadius: 8, fontWeight: 600, cursor: "pointer",
                              }}
                            >
                              확인
                            </button>
                          </div>
                          {totpMsg && <p style={{ marginTop: 10, color: totpMsg.includes("활성화") ? "#16a34a" : "#dc2626" }}>{totpMsg}</p>}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* FIDO2 탭 */}
              {tab === "fido" && (
                <div className="card">
                  <h3 style={{ marginBottom: 8 }}>FIDO2 / WebAuthn 생체인증</h3>
                  <p className="text-secondary" style={{ marginBottom: 20 }}>
                    지문, Face ID, 보안키(YubiKey 등)를 사용한 비밀번호 없는 강력한 인증입니다.
                  </p>

                  <div style={{
                    background: "#fffbeb", border: "1px solid #fcd34d",
                    borderRadius: 8, padding: 14, marginBottom: 20,
                  }}>
                    <p style={{ color: "#92400e", fontWeight: 500, marginBottom: 4 }}>브라우저 지원 필요</p>
                    <p style={{ color: "#b45309", fontSize: 13 }}>
                      FIDO2 등록/인증은 실제 브라우저의 WebAuthn API를 통해 이루어집니다.
                      Chrome, Firefox, Safari 최신 버전에서 지원됩니다.
                    </p>
                  </div>

                  {fidoCreds.length > 0 ? (
                    <div style={{ marginBottom: 20 }}>
                      <h4 style={{ marginBottom: 12 }}>등록된 인증 장치 ({fidoCreds.length}개)</h4>
                      {fidoCreds.map(cred => (
                        <div key={cred.id} style={{
                          border: "1px solid #e5e7eb", borderRadius: 8, padding: 14,
                          marginBottom: 8, display: "flex", justifyContent: "space-between", alignItems: "center",
                        }}>
                          <div>
                            <p style={{ fontWeight: 500 }}>{cred.name}</p>
                            <p style={{ fontSize: 12, color: "#6b7280" }}>
                              ID: {cred.credential_id_prefix}... · 유형: {cred.device_type}
                            </p>
                            <p style={{ fontSize: 12, color: "#9ca3af" }}>
                              마지막 사용: {cred.last_used_at ? new Date(cred.last_used_at).toLocaleDateString("ko-KR") : "미사용"}
                            </p>
                          </div>
                          <button
                            onClick={() => deleteCredential(cred.id)}
                            style={{
                              padding: "6px 12px", background: "#fef2f2", color: "#ef4444",
                              border: "1px solid #fca5a5", borderRadius: 6, cursor: "pointer", fontSize: 13,
                            }}
                          >
                            삭제
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{
                      background: "#f8fafc", borderRadius: 8, padding: 20,
                      textAlign: "center", marginBottom: 20,
                    }}>
                      <p style={{ color: "#6b7280" }}>등록된 FIDO2 인증 장치가 없습니다.</p>
                    </div>
                  )}

                  <p style={{ fontSize: 13, color: "#6b7280" }}>
                    FIDO2 장치 등록은 실제 브라우저 환경에서 <code>/api/v1/auth/fido/register/options</code> API를 통해 진행됩니다.
                    현재 등록된 장치 목록과 삭제 기능을 제공합니다.
                  </p>
                </div>
              )}

              {/* 보안 이벤트 내역 탭 */}
              {tab === "history" && (
                <div className="card">
                  <h3 style={{ marginBottom: 16 }}>보안 이벤트 내역 (최근 20건)</h3>
                  {history.length === 0 ? (
                    <p className="text-secondary">보안 이벤트가 없습니다.</p>
                  ) : (
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                        <thead>
                          <tr style={{ borderBottom: "2px solid #e5e7eb" }}>
                            <th style={{ textAlign: "left", padding: "8px 12px", color: "#6b7280" }}>일시</th>
                            <th style={{ textAlign: "left", padding: "8px 12px", color: "#6b7280" }}>방법</th>
                            <th style={{ textAlign: "left", padding: "8px 12px", color: "#6b7280" }}>리스크 점수</th>
                            <th style={{ textAlign: "left", padding: "8px 12px", color: "#6b7280" }}>결과</th>
                          </tr>
                        </thead>
                        <tbody>
                          {history.map((h, i) => (
                            <tr key={i} style={{ borderBottom: "1px solid #f3f4f6" }}>
                              <td style={{ padding: "8px 12px" }}>
                                {new Date(h.created_at).toLocaleString("ko-KR")}
                              </td>
                              <td style={{ padding: "8px 12px" }}>
                                <span style={{
                                  background: h.method === "totp" ? "#ede9fe" : "#dbeafe",
                                  color: h.method === "totp" ? "#6d28d9" : "#1d4ed8",
                                  padding: "2px 8px", borderRadius: 4, fontSize: 12,
                                }}>
                                  {h.method.toUpperCase()}
                                </span>
                              </td>
                              <td style={{ padding: "8px 12px" }}>
                                <span style={{
                                  color: h.risk_score >= 0.6 ? "#dc2626" : h.risk_score >= 0.3 ? "#d97706" : "#16a34a",
                                  fontWeight: 600,
                                }}>
                                  {(h.risk_score * 100).toFixed(0)}%
                                </span>
                              </td>
                              <td style={{ padding: "8px 12px" }}>
                                <span style={{
                                  background: h.verified ? "#f0fdf4" : "#fef2f2",
                                  color: h.verified ? "#16a34a" : "#dc2626",
                                  padding: "2px 8px", borderRadius: 4, fontSize: 12,
                                }}>
                                  {h.verified ? "인증 성공" : "대기/실패"}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </>
  );
}

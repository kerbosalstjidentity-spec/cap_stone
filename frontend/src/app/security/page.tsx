"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/hooks/useAuth";

type UserProfile = {
  user_id: string;
  email: string | null;
  nickname: string;
  totp_enabled: boolean;
  edu_level: string;
};

type StepUpHistory = {
  method: string;
  method_label?: string;
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

// ──────────────────────────────────────────────
// WebAuthn 헬퍼 (base64url ↔ ArrayBuffer)
// ──────────────────────────────────────────────

function base64urlToBuffer(base64url: string): ArrayBuffer {
  const base64 = base64url.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(base64.length + (4 - (base64.length % 4)) % 4, "=");
  const binary = atob(padded);
  const buffer = new ArrayBuffer(binary.length);
  const view = new Uint8Array(buffer);
  for (let i = 0; i < binary.length; i++) view[i] = binary.charCodeAt(i);
  return buffer;
}

function bufferToBase64url(buffer: ArrayBuffer): string {
  const view = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < view.byteLength; i++) binary += String.fromCharCode(view[i]);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

function SecurityContent() {
  const { accessToken } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [history, setHistory] = useState<StepUpHistory[]>([]);
  const [fidoCreds, setFidoCreds] = useState<FidoCredential[]>([]);
  const [tab, setTab] = useState<"overview" | "totp" | "fido" | "history">("overview");
  const [loading, setLoading] = useState(true);

  // TOTP 상태
  const [totpSetup, setTotpSetup] = useState<{ secret: string; qr_uri: string; qr_image: string } | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [totpMsg, setTotpMsg] = useState("");

  // FIDO2 상태
  const [fidoMsg, setFidoMsg] = useState("");
  const [fidoLoading, setFidoLoading] = useState(false);
  const [fidoDeviceName, setFidoDeviceName] = useState("");

  // 비밀번호 변경 상태
  const [pwForm, setPwForm] = useState({ current: "", next: "" });
  const [pwMsg, setPwMsg] = useState("");

  const authHeaders = { Authorization: `Bearer ${accessToken}` };

  useEffect(() => {
    if (!accessToken) { setLoading(false); return; }
    Promise.all([
      fetch("/api/v1/auth/me", { headers: authHeaders }).then(r => r.ok ? r.json() : null),
      fetch("/api/v1/auth/stepup/history", { headers: authHeaders }).then(r => r.ok ? r.json() : { history: [] }),
      fetch("/api/v1/auth/fido/credentials", { headers: authHeaders }).then(r => r.ok ? r.json() : []),
    ]).then(([prof, hist, creds]) => {
      setProfile(prof);
      setHistory(hist?.history ?? []);
      setFidoCreds(Array.isArray(creds) ? creds : []);
    }).finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  // ── TOTP ──────────────────────────────────────

  async function startTotpSetup() {
    const res = await fetch("/api/v1/auth/me/totp/setup", {
      method: "POST", headers: authHeaders,
    });
    if (res.ok) setTotpSetup(await res.json());
  }

  async function verifyTotp() {
    const res = await fetch("/api/v1/auth/me/totp/verify", {
      method: "POST",
      headers: { ...authHeaders, "Content-Type": "application/json" },
      body: JSON.stringify({ code: totpCode }),
    });
    const data = await res.json();
    if (res.ok) {
      setTotpMsg("TOTP 2FA가 활성화되었습니다! 이제 로그인 시 OTP 코드가 필요합니다.");
      setProfile(p => p ? { ...p, totp_enabled: true } : p);
      setTotpSetup(null);
      setTotpCode("");
    } else {
      setTotpMsg(data.detail || "코드가 올바르지 않습니다.");
    }
  }

  async function disableTotp() {
    const code = prompt("현재 OTP 코드를 입력하여 TOTP를 비활성화합니다:");
    if (!code) return;
    const res = await fetch("/api/v1/auth/me/totp/disable", {
      method: "POST",
      headers: { ...authHeaders, "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    if (res.ok) {
      setTotpMsg("TOTP가 비활성화되었습니다.");
      setProfile(p => p ? { ...p, totp_enabled: false } : p);
    }
  }

  // ── FIDO2 / WebAuthn ──────────────────────────

  async function registerFido() {
    if (!window.PublicKeyCredential) {
      setFidoMsg("이 브라우저는 WebAuthn을 지원하지 않습니다.");
      return;
    }
    setFidoLoading(true);
    setFidoMsg("");
    try {
      // 1) 등록 옵션 요청
      const optRes = await fetch("/api/v1/auth/fido/register/options", { headers: authHeaders });
      if (!optRes.ok) { setFidoMsg("등록 옵션을 가져오지 못했습니다."); return; }
      const opts = await optRes.json();

      // 2) 브라우저 WebAuthn API 호출 (실제 생체/PIN 인증)
      const credential = await navigator.credentials.create({
        publicKey: {
          challenge: base64urlToBuffer(opts.challenge),
          rp: { id: opts.rp_id, name: opts.rp_name },
          user: {
            id: new TextEncoder().encode(opts.user_id),
            name: opts.user_name,
            displayName: opts.user_name,
          },
          pubKeyCredParams: [
            { alg: -7, type: "public-key" },   // ES256
            { alg: -257, type: "public-key" },  // RS256
          ],
          timeout: opts.timeout ?? 60000,
          authenticatorSelection: {
            userVerification: "preferred",
            residentKey: "preferred",
          },
          attestation: "none",
        },
      }) as PublicKeyCredential | null;

      if (!credential) { setFidoMsg("인증 장치 등록이 취소되었습니다."); return; }

      const response = credential.response as AuthenticatorAttestationResponse;

      // 3) 백엔드로 결과 전송
      const verRes = await fetch("/api/v1/auth/fido/register/verify", {
        method: "POST",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({
          credential_id: bufferToBase64url(credential.rawId),
          client_data_json: bufferToBase64url(response.clientDataJSON),
          attestation_object: bufferToBase64url(response.attestationObject),
          device_name: fidoDeviceName || "내 인증 장치",
        }),
      });
      const verData = await verRes.json();
      if (!verRes.ok) { setFidoMsg(verData.detail || "등록 검증 실패"); return; }

      setFidoMsg("FIDO2 인증 장치가 성공적으로 등록되었습니다!");
      setFidoDeviceName("");

      // 목록 갱신
      const credsRes = await fetch("/api/v1/auth/fido/credentials", { headers: authHeaders });
      if (credsRes.ok) setFidoCreds(await credsRes.json());

      // 보안 점수 반영
      setProfile(p => p ? p : p);

    } catch (err: unknown) {
      if (err instanceof Error && err.name === "NotAllowedError") {
        setFidoMsg("사용자가 인증을 거부했거나 타임아웃이 발생했습니다.");
      } else {
        setFidoMsg("FIDO2 등록 중 오류가 발생했습니다: " + (err instanceof Error ? err.message : String(err)));
      }
    } finally {
      setFidoLoading(false);
    }
  }

  async function deleteCredential(id: number) {
    if (!confirm("이 인증 장치를 삭제하시겠습니까?")) return;
    await fetch(`/api/v1/auth/fido/credentials/${id}`, {
      method: "DELETE", headers: authHeaders,
    });
    setFidoCreds(creds => creds.filter(c => c.id !== id));
  }

  // ── 비밀번호 변경 ──────────────────────────────

  async function changePassword() {
    const res = await fetch("/api/v1/auth/me/change-password", {
      method: "POST",
      headers: { ...authHeaders, "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: pwForm.current, new_password: pwForm.next }),
    });
    const data = await res.json();
    setPwMsg(res.ok ? "비밀번호가 변경되었습니다." : (data.detail || "실패했습니다."));
    if (res.ok) setPwForm({ current: "", next: "" });
  }

  // ── 스타일 헬퍼 ───────────────────────────────

  const tabStyle = (t: string) => ({
    padding: "8px 16px", borderRadius: 6, cursor: "pointer", fontWeight: 500,
    background: tab === t ? "#6366f1" : "transparent",
    color: tab === t ? "#fff" : "#6b7280",
    border: "none",
  } as React.CSSProperties);

  const securityScore = profile
    ? (profile.totp_enabled ? 40 : 0) + (fidoCreds.length > 0 ? 40 : 0) + 20
    : 20;
  const scoreColor = securityScore >= 80 ? "#10b981" : securityScore >= 50 ? "#f59e0b" : "#ef4444";

  // 이벤트 색상
  const methodColor: Record<string, string> = {
    login: "#dbeafe", login_totp: "#ede9fe", totp: "#ede9fe",
    login_fail: "#fee2e2", totp_fail: "#fee2e2", fido: "#d1fae5",
  };
  const methodText: Record<string, string> = {
    login: "#1d4ed8", login_totp: "#6d28d9", totp: "#6d28d9",
    login_fail: "#dc2626", totp_fail: "#dc2626", fido: "#065f46",
  };

  return (
    <>
      <NavBar activePath="/security" />
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
              <div className="card" style={{ marginBottom: 16 }}>
                <h4 style={{ marginBottom: 12 }}>내 보안 점수</h4>
                <div style={{ textAlign: "center", padding: "8px 0" }}>
                  <div style={{
                    width: 80, height: 80, borderRadius: "50%",
                    border: `6px solid ${scoreColor}`,
                    display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 8px",
                  }}>
                    <span style={{ fontSize: 22, fontWeight: 700, color: scoreColor }}>{securityScore}</span>
                  </div>
                  <p style={{ fontSize: 13, color: "#6b7280" }}>
                    {securityScore >= 80 ? "우수" : securityScore >= 50 ? "보통" : "취약"}
                  </p>
                </div>
                <div style={{ borderTop: "1px solid #f3f4f6", paddingTop: 12, marginTop: 8 }}>
                  {[
                    { label: "기본 로그인", ok: true },
                    { label: "TOTP 2FA", ok: profile?.totp_enabled ?? false },
                    { label: "FIDO2 생체인증", ok: fidoCreds.length > 0 },
                  ].map(({ label, ok }) => (
                    <div key={label} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                      <span>{label}</span>
                      <span style={{ color: ok ? "#10b981" : "#9ca3af" }}>{ok ? "✓ +" : "○ +"}{ label === "기본 로그인" ? "20" : "40"}</span>
                    </div>
                  ))}
                </div>
              </div>

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
              {/* ── 개요 ── */}
              {tab === "overview" && (
                <div>
                  <div className="card" style={{ marginBottom: 16 }}>
                    <h3 style={{ marginBottom: 16 }}>계정 정보</h3>
                    {profile && (
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                        {[
                          { label: "이메일", value: profile.email },
                          { label: "닉네임", value: profile.nickname },
                          { label: "사용자 ID", value: profile.user_id },
                          { label: "교육 레벨", value: profile.edu_level },
                        ].map(({ label, value }) => (
                          <div key={label}>
                            <p style={{ fontSize: 12, color: "#9ca3af", marginBottom: 4 }}>{label}</p>
                            <p style={{ fontWeight: 500, fontSize: 13 }}>{value}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
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
                      {["current", "next"].map(k => (
                        <input
                          key={k}
                          type="password"
                          placeholder={k === "current" ? "현재 비밀번호" : "새 비밀번호 (8자 이상)"}
                          value={pwForm[k as keyof typeof pwForm]}
                          onChange={e => setPwForm(f => ({ ...f, [k]: e.target.value }))}
                          style={{ padding: "10px 14px", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 14 }}
                        />
                      ))}
                      <button
                        onClick={changePassword}
                        style={{ padding: "10px", background: "#374151", color: "#fff", border: "none", borderRadius: 8, fontWeight: 600, cursor: "pointer" }}
                      >
                        비밀번호 변경
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* ── TOTP ── */}
              {tab === "totp" && (
                <div className="card">
                  <h3 style={{ marginBottom: 8 }}>TOTP 2단계 인증</h3>
                  <p className="text-secondary" style={{ marginBottom: 20 }}>
                    Google Authenticator 또는 Authy 앱으로 6자리 일회용 코드를 생성해 로그인 시 추가 인증을 설정합니다.
                  </p>

                  {profile?.totp_enabled ? (
                    <div>
                      <div style={{ background: "#f0fdf4", border: "1px solid #86efac", borderRadius: 8, padding: 16, marginBottom: 20 }}>
                        <p style={{ color: "#16a34a", fontWeight: 600 }}>✓ TOTP 2FA가 활성화되어 있습니다</p>
                        <p style={{ color: "#15803d", fontSize: 13, marginTop: 4 }}>
                          로그인 시 OTP 앱의 6자리 코드가 추가로 요구됩니다.
                        </p>
                      </div>
                      {totpMsg && <p style={{ color: "#6b7280", marginBottom: 12 }}>{totpMsg}</p>}
                      <button
                        onClick={disableTotp}
                        style={{ padding: "10px 20px", background: "#ef4444", color: "#fff", border: "none", borderRadius: 8, fontWeight: 600, cursor: "pointer" }}
                      >
                        TOTP 비활성화
                      </button>
                    </div>
                  ) : (
                    <div>
                      {!totpSetup ? (
                        <button
                          onClick={startTotpSetup}
                          style={{ padding: "12px 24px", background: "#6366f1", color: "#fff", border: "none", borderRadius: 8, fontWeight: 600, cursor: "pointer" }}
                        >
                          TOTP 설정 시작
                        </button>
                      ) : (
                        <div>
                          <div style={{ background: "#f8fafc", borderRadius: 8, padding: 20, marginBottom: 16 }}>
                            <p style={{ fontWeight: 600, marginBottom: 16, fontSize: 15 }}>
                              Google Authenticator / Authy 앱으로 QR 코드를 스캔하세요
                            </p>

                            {/* QR 코드 이미지 */}
                            <div style={{ display: "flex", gap: 24, alignItems: "flex-start", flexWrap: "wrap" }}>
                              <div>
                                <img
                                  src={totpSetup.qr_image}
                                  alt="TOTP QR Code"
                                  style={{ width: 180, height: 180, border: "4px solid #e5e7eb", borderRadius: 8 }}
                                />
                                <p style={{ fontSize: 12, color: "#6b7280", marginTop: 6, textAlign: "center" }}>
                                  QR 코드 스캔
                                </p>
                              </div>
                              <div style={{ flex: 1, minWidth: 200 }}>
                                <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 8 }}>
                                  앱이 없다면 아래 키를 수동 입력하세요:
                                </p>
                                <div style={{
                                  background: "#1e293b", color: "#e2e8f0", padding: "10px 14px", borderRadius: 6,
                                  fontFamily: "monospace", fontSize: 13, wordBreak: "break-all", letterSpacing: 2,
                                }}>
                                  {totpSetup.secret}
                                </div>
                              </div>
                            </div>
                          </div>

                          <p style={{ fontWeight: 500, marginBottom: 8 }}>앱에서 생성된 6자리 코드 입력:</p>
                          <div style={{ display: "flex", gap: 8 }}>
                            <input
                              type="text"
                              inputMode="numeric"
                              placeholder="000000"
                              value={totpCode}
                              onChange={e => setTotpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                              maxLength={6}
                              style={{ flex: 1, padding: "12px 14px", border: "2px solid #e5e7eb", borderRadius: 8, fontSize: 22, letterSpacing: 8, textAlign: "center", fontWeight: 700 }}
                            />
                            <button
                              onClick={verifyTotp}
                              disabled={totpCode.length < 6}
                              style={{
                                padding: "10px 20px", background: "#10b981", color: "#fff",
                                border: "none", borderRadius: 8, fontWeight: 600, cursor: totpCode.length < 6 ? "not-allowed" : "pointer",
                                opacity: totpCode.length < 6 ? 0.6 : 1,
                              }}
                            >
                              확인
                            </button>
                          </div>
                          {totpMsg && (
                            <p style={{ marginTop: 10, color: totpMsg.includes("활성화") ? "#16a34a" : "#dc2626" }}>
                              {totpMsg}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* ── FIDO2 ── */}
              {tab === "fido" && (
                <div className="card">
                  <h3 style={{ marginBottom: 8 }}>FIDO2 / WebAuthn 생체인증</h3>
                  <p className="text-secondary" style={{ marginBottom: 20 }}>
                    Windows Hello, 지문, Face ID, YubiKey 등을 사용한 비밀번호 없는 강력한 인증입니다.
                  </p>

                  {/* 장치 등록 폼 */}
                  <div style={{ background: "#f8fafc", borderRadius: 8, padding: 16, marginBottom: 20 }}>
                    <h4 style={{ marginBottom: 12 }}>새 인증 장치 등록</h4>
                    <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                      <input
                        type="text"
                        placeholder="장치 이름 (예: 내 노트북 지문)"
                        value={fidoDeviceName}
                        onChange={e => setFidoDeviceName(e.target.value)}
                        style={{ flex: 1, padding: "10px 14px", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 14 }}
                      />
                    </div>
                    <button
                      onClick={registerFido}
                      disabled={fidoLoading}
                      style={{
                        padding: "12px 24px", background: fidoLoading ? "#9ca3af" : "#6366f1",
                        color: "#fff", border: "none", borderRadius: 8, fontWeight: 600,
                        cursor: fidoLoading ? "not-allowed" : "pointer", width: "100%",
                      }}
                    >
                      {fidoLoading ? "등록 중... (장치 프롬프트를 확인하세요)" : "🔑 인증 장치 등록 시작"}
                    </button>
                    {fidoMsg && (
                      <p style={{
                        marginTop: 10, fontSize: 14,
                        color: fidoMsg.includes("성공") ? "#16a34a" : "#dc2626",
                      }}>
                        {fidoMsg}
                      </p>
                    )}
                    <p style={{ fontSize: 12, color: "#9ca3af", marginTop: 8 }}>
                      Chrome, Edge, Firefox 최신 버전 + HTTPS 또는 localhost 환경에서 동작합니다.
                    </p>
                  </div>

                  {/* 등록된 장치 목록 */}
                  {fidoCreds.length > 0 ? (
                    <div>
                      <h4 style={{ marginBottom: 12 }}>등록된 인증 장치 ({fidoCreds.length}개)</h4>
                      {fidoCreds.map(cred => (
                        <div key={cred.id} style={{
                          border: "1px solid #e5e7eb", borderRadius: 8, padding: 14,
                          marginBottom: 8, display: "flex", justifyContent: "space-between", alignItems: "center",
                        }}>
                          <div>
                            <p style={{ fontWeight: 500 }}>🔑 {cred.name}</p>
                            <p style={{ fontSize: 12, color: "#6b7280" }}>
                              ID: {cred.credential_id_prefix}... · 유형: {cred.device_type}
                            </p>
                            <p style={{ fontSize: 12, color: "#9ca3af" }}>
                              마지막 사용: {cred.last_used_at ? new Date(cred.last_used_at).toLocaleDateString("ko-KR") : "미사용"} ·
                              등록일: {new Date(cred.created_at).toLocaleDateString("ko-KR")}
                            </p>
                          </div>
                          <button
                            onClick={() => deleteCredential(cred.id)}
                            style={{ padding: "6px 12px", background: "#fef2f2", color: "#ef4444", border: "1px solid #fca5a5", borderRadius: 6, cursor: "pointer", fontSize: 13 }}
                          >
                            삭제
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ background: "#f8fafc", borderRadius: 8, padding: 20, textAlign: "center" }}>
                      <p style={{ color: "#6b7280" }}>등록된 FIDO2 인증 장치가 없습니다.</p>
                    </div>
                  )}
                </div>
              )}

              {/* ── 보안 이벤트 내역 ── */}
              {tab === "history" && (
                <div className="card">
                  <h3 style={{ marginBottom: 4 }}>보안 이벤트 내역</h3>
                  <p className="text-secondary" style={{ marginBottom: 16, fontSize: 13 }}>
                    최근 30건의 로그인 및 인증 이벤트입니다.
                  </p>
                  {history.length === 0 ? (
                    <p className="text-secondary">보안 이벤트가 없습니다. 로그아웃 후 다시 로그인하면 기록됩니다.</p>
                  ) : (
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                        <thead>
                          <tr style={{ borderBottom: "2px solid #e5e7eb" }}>
                            {["일시", "이벤트 유형", "리스크 점수", "결과"].map(h => (
                              <th key={h} style={{ textAlign: "left", padding: "8px 12px", color: "#6b7280" }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {history.map((h, i) => (
                            <tr key={i} style={{ borderBottom: "1px solid #f3f4f6" }}>
                              <td style={{ padding: "8px 12px", fontSize: 13 }}>
                                {new Date(h.created_at).toLocaleString("ko-KR")}
                              </td>
                              <td style={{ padding: "8px 12px" }}>
                                <span style={{
                                  background: methodColor[h.method] ?? "#f3f4f6",
                                  color: methodText[h.method] ?? "#374151",
                                  padding: "2px 8px", borderRadius: 4, fontSize: 12, whiteSpace: "nowrap",
                                }}>
                                  {h.method_label ?? h.method}
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
                                  {h.verified ? "성공" : "실패"}
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

export default function SecurityPage() {
  return (
    <AuthGuard>
      <SecurityContent />
    </AuthGuard>
  );
}

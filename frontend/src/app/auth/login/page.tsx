"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";

function base64urlToBuffer(base64url: string): ArrayBuffer {
  const base64 = base64url.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(base64.length + (4 - (base64.length % 4)) % 4, "=");
  const binary = atob(padded);
  const buf = new ArrayBuffer(binary.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < binary.length; i++) view[i] = binary.charCodeAt(i);
  return buf;
}

function bufferToBase64url(buffer: ArrayBuffer): string {
  const view = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < view.byteLength; i++) binary += String.fromCharCode(view[i]);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

type Step = "password" | "choose" | "totp" | "fido";

export default function LoginPage() {
  const router = useRouter();
  const { isLoggedIn, isLoading: authLoading } = useAuth();
  const [step, setStep] = useState<Step>("password");
  const [form, setForm] = useState({ email: "", password: "" });
  const [totpCode, setTotpCode] = useState("");
  const [preAuthToken, setPreAuthToken] = useState("");
  const [totpRequired, setTotpRequired] = useState(false);
  const [fidoAvailable, setFidoAvailable] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const totpInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!authLoading && isLoggedIn) router.replace("/dashboard");
  }, [authLoading, isLoggedIn, router]);

  useEffect(() => {
    if (step === "totp") setTimeout(() => totpInputRef.current?.focus(), 100);
  }, [step]);

  // ── 1단계: 비밀번호 ──────────────────────────

  async function handlePasswordSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail;
        setError(Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join(" / ")
          : typeof detail === "string" ? detail : "로그인에 실패했습니다.");
        return;
      }

      if (data.totp_required || data.fido_available) {
        setPreAuthToken(data.pre_auth_token);
        setTotpRequired(data.totp_required);
        setFidoAvailable(data.fido_available);

        // 둘 다 있으면 선택 화면, 하나만 있으면 바로 이동
        if (data.totp_required && data.fido_available) {
          setStep("choose");
        } else if (data.fido_available) {
          setStep("fido");
        } else {
          setStep("totp");
        }
      } else {
        _saveAndRedirect(data);
      }
    } catch {
      setError("서버에 연결할 수 없습니다.");
    } finally {
      setLoading(false);
    }
  }

  // ── 2단계: TOTP ──────────────────────────────

  async function handleTotpSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/v1/auth/login/totp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pre_auth_token: preAuthToken, code: totpCode }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "OTP 코드가 올바르지 않습니다."); setTotpCode(""); return; }
      _saveAndRedirect(data);
    } catch {
      setError("서버에 연결할 수 없습니다.");
    } finally {
      setLoading(false);
    }
  }

  // ── 2단계: FIDO2 ─────────────────────────────

  async function handleFidoLogin() {
    if (!window.PublicKeyCredential) {
      setError("이 브라우저는 WebAuthn을 지원하지 않습니다.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      // 챌린지 요청
      const optRes = await fetch("/api/v1/auth/fido/login/options", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pre_auth_token: preAuthToken }),
      });
      if (!optRes.ok) { setError("챌린지 요청 실패. 다시 시도하세요."); return; }
      const opts = await optRes.json();

      // 브라우저 WebAuthn 인증 실행 (지문 / PIN / 보안키)
      const credential = await navigator.credentials.get({
        publicKey: {
          challenge: base64urlToBuffer(opts.challenge),
          rpId: opts.rp_id,
          allowCredentials: opts.allow_credentials.map((c: { id: string }) => ({
            id: base64urlToBuffer(c.id),
            type: "public-key" as const,
          })),
          timeout: opts.timeout ?? 60000,
          userVerification: "preferred" as const,
        },
      }) as PublicKeyCredential | null;

      if (!credential) { setError("인증이 취소되었습니다."); return; }
      const response = credential.response as AuthenticatorAssertionResponse;

      // 검증 요청
      const verRes = await fetch("/api/v1/auth/fido/login/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pre_auth_token: preAuthToken,
          credential_id: bufferToBase64url(credential.rawId),
          client_data_json: bufferToBase64url(response.clientDataJSON),
          authenticator_data: bufferToBase64url(response.authenticatorData),
          signature: bufferToBase64url(response.signature),
        }),
      });
      const verData = await verRes.json();
      if (!verRes.ok) { setError(verData.detail || "FIDO2 인증 실패"); return; }
      _saveAndRedirect(verData);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "NotAllowedError") {
        setError("사용자가 인증을 거부했거나 타임아웃이 발생했습니다.");
      } else {
        setError("FIDO2 인증 오류: " + (err instanceof Error ? err.message : String(err)));
      }
    } finally {
      setLoading(false);
    }
  }

  function _saveAndRedirect(data: { access_token: string; refresh_token: string; user_id: string; nickname: string }) {
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    localStorage.setItem("user_id", data.user_id);
    localStorage.setItem("nickname", data.nickname);
    router.push("/dashboard");
  }

  function goBack() { setStep("password"); setError(""); setTotpCode(""); }

  // ── 공통 스타일 ───────────────────────────────

  const btnPrimary: React.CSSProperties = {
    padding: "12px", background: "#6366f1", color: "#fff",
    border: "none", borderRadius: 8, fontWeight: 600, fontSize: 15,
    cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.7 : 1, width: "100%",
  };
  const btnSecondary: React.CSSProperties = {
    padding: "10px", background: "transparent", color: "#6b7280",
    border: "1px solid #e5e7eb", borderRadius: 8, cursor: "pointer", fontSize: 14, width: "100%",
  };
  const errorBox = error ? (
    <div style={{
      background: "#fef2f2", border: "1px solid #fca5a5",
      borderRadius: 8, padding: "12px 16px", marginBottom: 16, color: "#dc2626", textAlign: "center",
    }}>
      {error}
    </div>
  ) : null;

  return (
    <>
      <nav>
        <div className="container">
          <h2><Link href="/" style={{ textDecoration: "none", color: "inherit" }}>ConsumePattern</Link></h2>
        </div>
      </nav>
      <main className="container" style={{ maxWidth: 440, paddingTop: 80 }}>
        <div className="card">

          {/* ── 1단계: 비밀번호 ── */}
          {step === "password" && (
            <>
              <h2 style={{ marginBottom: 8 }}>로그인</h2>
              <p className="text-secondary" style={{ marginBottom: 24 }}>소비 패턴 분석 서비스에 오신 걸 환영합니다.</p>
              {errorBox}
              <form onSubmit={handlePasswordSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div>
                  <label style={{ display: "block", marginBottom: 6, fontWeight: 500 }}>이메일</label>
                  <input type="email" value={form.email}
                    onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                    placeholder="your@email.com" required
                    style={{ width: "100%", padding: "10px 14px", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 14, boxSizing: "border-box" }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", marginBottom: 6, fontWeight: 500 }}>비밀번호</label>
                  <input type="password" value={form.password}
                    onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                    placeholder="비밀번호 입력" required
                    style={{ width: "100%", padding: "10px 14px", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 14, boxSizing: "border-box" }}
                  />
                </div>
                <button type="submit" disabled={loading} style={btnPrimary}>
                  {loading ? "확인 중..." : "로그인"}
                </button>
              </form>
              <p style={{ textAlign: "center", marginTop: 20, color: "#6b7280" }}>
                계정이 없으신가요?{" "}
                <Link href="/auth/register" style={{ color: "#6366f1", fontWeight: 500 }}>회원가입</Link>
              </p>
            </>
          )}

          {/* ── 2단계 선택: TOTP vs FIDO2 ── */}
          {step === "choose" && (
            <>
              <div style={{ textAlign: "center", marginBottom: 24 }}>
                <div style={{ width: 56, height: 56, borderRadius: "50%", background: "#ede9fe", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 12px", fontSize: 24 }}>
                  🛡️
                </div>
                <h2 style={{ marginBottom: 6 }}>2단계 인증</h2>
                <p className="text-secondary" style={{ fontSize: 14 }}>인증 방법을 선택하세요.</p>
              </div>
              {errorBox}
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {fidoAvailable && (
                  <button
                    onClick={() => { setError(""); setStep("fido"); }}
                    style={{
                      padding: "16px", background: "#f0fdf4", color: "#065f46",
                      border: "2px solid #6ee7b7", borderRadius: 10, fontWeight: 600,
                      cursor: "pointer", fontSize: 15, textAlign: "left",
                    }}
                  >
                    <span style={{ fontSize: 20, marginRight: 10 }}>🔑</span>
                    생체인증 / 보안키 (FIDO2)
                    <p style={{ fontSize: 12, color: "#6b7280", marginTop: 4, fontWeight: 400 }}>
                      Windows Hello, 지문, PIN, YubiKey 등을 사용합니다.
                    </p>
                  </button>
                )}
                {totpRequired && (
                  <button
                    onClick={() => { setError(""); setStep("totp"); }}
                    style={{
                      padding: "16px", background: "#f5f3ff", color: "#4c1d95",
                      border: "2px solid #c4b5fd", borderRadius: 10, fontWeight: 600,
                      cursor: "pointer", fontSize: 15, textAlign: "left",
                    }}
                  >
                    <span style={{ fontSize: 20, marginRight: 10 }}>📱</span>
                    OTP 인증 앱 (TOTP)
                    <p style={{ fontSize: 12, color: "#6b7280", marginTop: 4, fontWeight: 400 }}>
                      Google Authenticator, Authy 앱의 6자리 코드를 사용합니다.
                    </p>
                  </button>
                )}
                <button type="button" onClick={goBack} style={btnSecondary}>← 이전으로</button>
              </div>
            </>
          )}

          {/* ── 2단계: TOTP ── */}
          {step === "totp" && (
            <>
              <div style={{ textAlign: "center", marginBottom: 20 }}>
                <div style={{ width: 56, height: 56, borderRadius: "50%", background: "#ede9fe", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 12px", fontSize: 24 }}>
                  📱
                </div>
                <h2 style={{ marginBottom: 6 }}>OTP 코드 입력</h2>
                <p className="text-secondary" style={{ fontSize: 14 }}>Google Authenticator 앱의 6자리 코드를 입력하세요.</p>
              </div>
              {errorBox}
              <form onSubmit={handleTotpSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <input
                  ref={totpInputRef}
                  type="text" inputMode="numeric" pattern="[0-9]{6}"
                  value={totpCode}
                  onChange={e => setTotpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="000000" maxLength={6} required
                  style={{ width: "100%", padding: "16px 14px", border: "2px solid #e5e7eb", borderRadius: 8, fontSize: 28, letterSpacing: 12, textAlign: "center", fontWeight: 700, boxSizing: "border-box" }}
                />
                <button type="submit" disabled={loading || totpCode.length < 6}
                  style={{ ...btnPrimary, opacity: (loading || totpCode.length < 6) ? 0.7 : 1, cursor: (loading || totpCode.length < 6) ? "not-allowed" : "pointer" }}>
                  {loading ? "확인 중..." : "인증 완료"}
                </button>
                <button type="button" onClick={() => setStep(fidoAvailable ? "choose" : "password")} style={btnSecondary}>
                  ← 이전으로
                </button>
              </form>
            </>
          )}

          {/* ── 2단계: FIDO2 ── */}
          {step === "fido" && (
            <>
              <div style={{ textAlign: "center", marginBottom: 24 }}>
                <div style={{ width: 56, height: 56, borderRadius: "50%", background: "#f0fdf4", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 12px", fontSize: 24 }}>
                  🔑
                </div>
                <h2 style={{ marginBottom: 6 }}>생체인증 / 보안키</h2>
                <p className="text-secondary" style={{ fontSize: 14 }}>
                  등록된 장치로 인증합니다.<br />
                  Windows Hello, 지문, PIN 또는 보안키를 사용하세요.
                </p>
              </div>
              {errorBox}
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <button
                  onClick={handleFidoLogin}
                  disabled={loading}
                  style={{ ...btnPrimary, background: loading ? "#9ca3af" : "#059669", padding: "14px" }}
                >
                  {loading ? "장치 프롬프트를 확인하세요..." : "🔑 생체인증으로 로그인"}
                </button>
                <button type="button" onClick={() => setStep(totpRequired ? "choose" : "password")} style={btnSecondary}>
                  ← 이전으로
                </button>
              </div>
            </>
          )}

        </div>
      </main>
    </>
  );
}

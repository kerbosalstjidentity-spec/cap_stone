"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/hooks/useAuth";

type Consent = {
  consent_id: string;
  provider: string;
  data_types: string[];
  purpose: string;
  granted_at: number;
  expires_at: number;
  status: string;
};

type PIDInfo = {
  has_pid: boolean;
  pid?: string;
  version?: number;
  needs_rotation?: boolean;
  rotation_days?: number;
  history_count?: number;
};

function MyDataContent() {
  const { userId, accessToken } = useAuth();
  const [consents, setConsents] = useState<Consent[]>([]);
  const [pidInfo, setPidInfo] = useState<PIDInfo | null>(null);
  const [tab, setTab] = useState<"consents" | "privacy">("consents");
  const [showForm, setShowForm] = useState(false);
  const [formProvider, setFormProvider] = useState("");
  const [formPurpose, setFormPurpose] = useState("spending_analysis");
  const [formDataTypes, setFormDataTypes] = useState<string[]>(["transactions"]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  };

  const fetchConsents = async () => {
    if (!userId) return;
    try {
      const res = await fetch(`/api/v1/security/mydata/consents/${userId}`, { headers });
      if (!res.ok) { setError(`Failed to fetch consents: ${res.status}`); return; }
      const data = await res.json();
      setConsents(data.consents || []);
    } catch { setError("Network error: unable to fetch consents"); }
  };

  const fetchPID = async () => {
    if (!userId) return;
    try {
      const res = await fetch(`/api/v1/security/privacy/pid/${userId}`, { headers });
      if (res.ok) setPidInfo(await res.json());
    } catch { /* PID fetch is optional */ }
  };

  const grantConsent = async () => {
    if (!userId || !formProvider) return;
    setError("");
    try {
      const res = await fetch("/api/v1/security/mydata/consent", {
        method: "POST",
        headers,
        body: JSON.stringify({
          user_id: userId,
          provider: formProvider,
          data_types: formDataTypes,
          purpose: formPurpose,
          duration_days: 365,
        }),
      });
      if (!res.ok) { setError(`Consent grant failed: ${res.status}`); return; }
      setShowForm(false);
      setFormProvider("");
      fetchConsents();
    } catch { setError("Network error: unable to grant consent"); }
  };

  const revokeConsent = async (consentId: string) => {
    setError("");
    try {
      const res = await fetch(`/api/v1/security/mydata/revoke/${consentId}`, {
        method: "POST",
        headers,
      });
      if (!res.ok) { setError(`Revoke failed: ${res.status}`); return; }
      fetchConsents();
    } catch { setError("Network error: unable to revoke consent"); }
  };

  const generatePID = async () => {
    if (!userId) return;
    try {
      const res = await fetch("/api/v1/security/privacy/pid/generate", {
        method: "POST",
        headers,
        body: JSON.stringify({ user_id: userId, rotation_days: 90 }),
      });
      if (!res.ok) { setError(`PID generation failed: ${res.status}`); return; }
      fetchPID();
    } catch { setError("Network error: unable to generate PID"); }
  };

  useEffect(() => {
    if (!userId) return;
    Promise.all([fetchConsents(), fetchPID()]).finally(() => setLoading(false));
  }, [userId]);

  const dataTypeOptions = [
    { value: "transactions", label: "Transaction History" },
    { value: "balance", label: "Account Balance" },
    { value: "loan", label: "Loan Information" },
    { value: "insurance", label: "Insurance Data" },
    { value: "investment", label: "Investment Portfolio" },
  ];

  const statusColor = (status: string) => {
    switch (status) {
      case "active": return "#10b981";
      case "expired": return "#f59e0b";
      case "revoked": return "#ef4444";
      default: return "#6b7280";
    }
  };

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "24px 16px" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
        MyData & Privacy Management
      </h1>
      {error && (
        <div style={{
          background: "#fef2f2", color: "#dc2626", padding: 12,
          borderRadius: 8, marginBottom: 16, fontSize: 14,
        }}>
          {error}
        </div>
      )}
      <p style={{ color: "#6b7280", marginBottom: 24 }}>
        SRS 5,9 - Open Banking Data Consent / SRS 1,5,8 - PID Management
      </p>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
        {(["consents", "privacy"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "8px 20px", borderRadius: 8, border: "none",
              fontWeight: 600, cursor: "pointer",
              background: tab === t ? "#4f46e5" : "#f3f4f6",
              color: tab === t ? "white" : "#4b5563",
            }}
          >
            {t === "consents" ? "MyData Consent" : "Privacy / PID"}
          </button>
        ))}
      </div>

      {loading ? (
        <p style={{ textAlign: "center", color: "#9ca3af" }}>Loading...</p>
      ) : tab === "consents" ? (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <h2 style={{ fontSize: 18, fontWeight: 600 }}>
              Data Sharing Consents ({consents.length})
            </h2>
            <button
              onClick={() => setShowForm(!showForm)}
              style={{
                padding: "8px 16px", borderRadius: 8,
                background: "#4f46e5", color: "white",
                border: "none", cursor: "pointer", fontWeight: 600,
              }}
            >
              + New Consent
            </button>
          </div>

          {showForm && (
            <div style={{
              background: "#f9fafb", borderRadius: 12, padding: 20,
              marginBottom: 20, border: "1px solid #e5e7eb",
            }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
                <div>
                  <label style={{ fontSize: 13, fontWeight: 600, display: "block", marginBottom: 4 }}>
                    Financial Provider
                  </label>
                  <input
                    value={formProvider}
                    onChange={(e) => setFormProvider(e.target.value)}
                    placeholder="e.g. KB Kookmin Bank"
                    style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: "1px solid #d1d5db" }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 13, fontWeight: 600, display: "block", marginBottom: 4 }}>
                    Purpose
                  </label>
                  <select
                    value={formPurpose}
                    onChange={(e) => setFormPurpose(e.target.value)}
                    style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: "1px solid #d1d5db" }}
                  >
                    <option value="spending_analysis">Spending Analysis</option>
                    <option value="credit_score">Credit Score</option>
                    <option value="fds">Fraud Detection</option>
                    <option value="insurance">Insurance</option>
                  </select>
                </div>
              </div>
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 13, fontWeight: 600, display: "block", marginBottom: 4 }}>
                  Data Types
                </label>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {dataTypeOptions.map((dt) => (
                    <label key={dt.value} style={{
                      display: "flex", alignItems: "center", gap: 4,
                      padding: "4px 10px", borderRadius: 6,
                      background: formDataTypes.includes(dt.value) ? "#eef2ff" : "#f9fafb",
                      border: `1px solid ${formDataTypes.includes(dt.value) ? "#818cf8" : "#e5e7eb"}`,
                      cursor: "pointer", fontSize: 13,
                    }}>
                      <input
                        type="checkbox"
                        checked={formDataTypes.includes(dt.value)}
                        onChange={(e) => {
                          if (e.target.checked) setFormDataTypes([...formDataTypes, dt.value]);
                          else setFormDataTypes(formDataTypes.filter((d) => d !== dt.value));
                        }}
                      />
                      {dt.label}
                    </label>
                  ))}
                </div>
              </div>
              <button
                onClick={grantConsent}
                style={{
                  padding: "10px 24px", borderRadius: 8,
                  background: "#10b981", color: "white",
                  border: "none", cursor: "pointer", fontWeight: 600,
                }}
              >
                Grant Consent
              </button>
            </div>
          )}

          {consents.length === 0 ? (
            <p style={{ textAlign: "center", color: "#9ca3af", padding: 40 }}>
              No data sharing consents registered
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {consents.map((c) => (
                <div
                  key={c.consent_id}
                  style={{
                    background: "white", borderRadius: 12, padding: 16,
                    border: "1px solid #e5e7eb",
                    borderLeft: `4px solid ${statusColor(c.status)}`,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                    <div>
                      <span style={{ fontWeight: 700, marginRight: 12 }}>{c.provider}</span>
                      <span style={{
                        fontSize: 12, fontWeight: 600,
                        color: statusColor(c.status),
                        background: `${statusColor(c.status)}15`,
                        padding: "2px 8px", borderRadius: 12,
                      }}>
                        {c.status.toUpperCase()}
                      </span>
                    </div>
                    {c.status === "active" && (
                      <button
                        onClick={() => revokeConsent(c.consent_id)}
                        style={{
                          padding: "4px 12px", borderRadius: 6,
                          background: "#fef2f2", color: "#ef4444",
                          border: "1px solid #fecaca", cursor: "pointer",
                          fontSize: 12, fontWeight: 600,
                        }}
                      >
                        Revoke
                      </button>
                    )}
                  </div>
                  <div style={{ fontSize: 13, color: "#6b7280", display: "flex", gap: 16 }}>
                    <span>Purpose: {c.purpose}</span>
                    <span>Data: {c.data_types.join(", ")}</span>
                  </div>
                  <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>
                    Granted: {new Date(c.granted_at * 1000).toLocaleDateString("ko-KR")}
                    {" | "}
                    Expires: {new Date(c.expires_at * 1000).toLocaleDateString("ko-KR")}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        /* Privacy / PID Tab */
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>
            Pseudonym ID (PID) Management
          </h2>
          <p style={{ color: "#6b7280", marginBottom: 20, fontSize: 14 }}>
            SRS 1,5,8: Pseudonymous identity for privacy-preserving transactions.
            PID is rotated periodically to prevent long-term tracking.
          </p>

          <div style={{
            background: "white", borderRadius: 12, padding: 24,
            border: "1px solid #e5e7eb", marginBottom: 20,
          }}>
            {pidInfo?.has_pid ? (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                  <div>
                    <div style={{ fontSize: 13, color: "#6b7280" }}>Current PID</div>
                    <div style={{ fontSize: 18, fontWeight: 700, fontFamily: "monospace" }}>
                      {pidInfo.pid}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 13, color: "#6b7280" }}>Version</div>
                    <div style={{ fontSize: 18, fontWeight: 700 }}>v{pidInfo.version}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 13, color: "#6b7280" }}>Rotation Period</div>
                    <div style={{ fontSize: 16, fontWeight: 600 }}>
                      {pidInfo.rotation_days} days
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 13, color: "#6b7280" }}>Status</div>
                    <div style={{
                      fontSize: 16, fontWeight: 600,
                      color: pidInfo.needs_rotation ? "#f59e0b" : "#10b981",
                    }}>
                      {pidInfo.needs_rotation ? "Rotation Needed" : "Active"}
                    </div>
                  </div>
                </div>
                {pidInfo.needs_rotation && (
                  <button
                    onClick={generatePID}
                    style={{
                      marginTop: 16, padding: "10px 24px", borderRadius: 8,
                      background: "#f59e0b", color: "white",
                      border: "none", cursor: "pointer", fontWeight: 600,
                    }}
                  >
                    Rotate PID Now
                  </button>
                )}
                <div style={{ marginTop: 12, fontSize: 13, color: "#9ca3af" }}>
                  Previous PID versions: {pidInfo.history_count || 0}
                </div>
              </>
            ) : (
              <div style={{ textAlign: "center", padding: 20 }}>
                <p style={{ color: "#6b7280", marginBottom: 16 }}>
                  No Pseudonym ID generated yet.
                </p>
                <button
                  onClick={generatePID}
                  style={{
                    padding: "12px 32px", borderRadius: 8,
                    background: "#4f46e5", color: "white",
                    border: "none", cursor: "pointer", fontWeight: 600,
                  }}
                >
                  Generate PID
                </button>
              </div>
            )}
          </div>

          <div style={{
            background: "#eff6ff", borderRadius: 12, padding: 20,
            border: "1px solid #bfdbfe",
          }}>
            <h3 style={{ fontWeight: 600, marginBottom: 8 }}>How PID Works</h3>
            <ul style={{ fontSize: 14, color: "#4b5563", lineHeight: 1.8, paddingLeft: 20 }}>
              <li>Your real identity is replaced with a cryptographic pseudonym</li>
              <li>PID is rotated every {pidInfo?.rotation_days || 90} days automatically</li>
              <li>External parties can only see your PID, never your real ID</li>
              <li>Prevents long-term behavioral tracking across services</li>
              <li>Based on SRS 1 (Blockchain HO Auth) and SRS 8 (EABEHP) requirements</li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

export default function MyDataPage() {
  return (
    <AuthGuard>
      <NavBar />
      <MyDataContent />
    </AuthGuard>
  );
}

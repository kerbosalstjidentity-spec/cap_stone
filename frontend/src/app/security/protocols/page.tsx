"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/hooks/useAuth";

type Protocol = {
  id: string;
  name: string;
  srs: string;
  description: string;
  phases: string[];
};

type BenchmarkResult = {
  avg_latency_ms: number;
  ops_per_sec: number;
  phases: number;
};

function ProtocolsContent() {
  const { accessToken } = useAuth();
  const [protocols, setProtocols] = useState<Protocol[]>([]);
  const [benchmarks, setBenchmarks] = useState<Record<string, BenchmarkResult>>({});
  const [loading, setLoading] = useState(true);
  const [benchmarking, setBenchmarking] = useState(false);
  const [abacResult, setAbacResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [abacForm, setAbacForm] = useState({
    user_role: "analyst",
    clearance: "MEDIUM",
    location: "internal",
    device_type: "desktop",
    mfa_verified: true,
    resource_sensitivity: "HIGH",
  });

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  };

  const fetchProtocols = async () => {
    setError("");
    try {
      const res = await fetch("/api/v1/security/protocols/overview", { headers });
      if (!res.ok) { setError(`Failed to load protocols: ${res.status}`); return; }
      const data = await res.json();
      setProtocols(data.protocols || []);
    } catch { setError("Network error: unable to load protocols"); }
    setLoading(false);
  };

  const runBenchmark = async () => {
    setBenchmarking(true);
    setError("");
    try {
      const res = await fetch("/api/v1/security/protocols/benchmark", { headers });
      if (!res.ok) { setError(`Benchmark failed: ${res.status}`); return; }
      const data = await res.json();
      setBenchmarks(data.protocols || {});
    } catch { setError("Network error: unable to run benchmark"); }
    setBenchmarking(false);
  };

  const testABAC = async () => {
    setError("");
    try {
      const res = await fetch("/api/v1/security/abac/evaluate", {
        method: "POST",
        headers,
        body: JSON.stringify(abacForm),
      });
      if (!res.ok) { setError(`ABAC test failed: ${res.status}`); return; }
      setAbacResult(await res.json());
    } catch { setError("Network error: unable to test ABAC"); }
  };

  useEffect(() => { fetchProtocols(); }, []);

  const srsColor = (srs: string) => {
    const colors: Record<string, string> = {
      "SRS 2": "#ef4444", "SRS 5": "#f59e0b", "SRS 6": "#10b981",
      "SRS 7": "#3b82f6", "SRS 8": "#8b5cf6", "SRS 10": "#ec4899",
    };
    return colors[srs] || "#6b7280";
  };

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 16px" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
        Security Protocols & ABAC Test
      </h1>
      <p style={{ color: "#6b7280", marginBottom: 24 }}>
        SRS 2,3,5,6,7,8,10 - Protocol Simulation & Fine-Grained Access Control
      </p>

      {error && (
        <div style={{
          background: "#fef2f2", color: "#dc2626", padding: 12,
          borderRadius: 8, marginBottom: 16, fontSize: 14,
        }}>
          {error}
        </div>
      )}

      {/* Protocol Cards */}
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12 }}>Security Protocols</h2>
      {loading ? (
        <p style={{ color: "#9ca3af" }}>Loading...</p>
      ) : (
        <div style={{
          display: "grid", gridTemplateColumns: "repeat(3, 1fr)",
          gap: 16, marginBottom: 32,
        }}>
          {protocols.map((p) => (
            <div
              key={p.id}
              style={{
                background: "white", borderRadius: 12, padding: 20,
                border: "1px solid #e5e7eb",
                borderTop: `3px solid ${srsColor(p.srs)}`,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                <span style={{ fontWeight: 700, fontSize: 15 }}>{p.name}</span>
                <span style={{
                  fontSize: 11, fontWeight: 700, color: srsColor(p.srs),
                  background: `${srsColor(p.srs)}15`,
                  padding: "2px 8px", borderRadius: 8,
                }}>
                  {p.srs}
                </span>
              </div>
              <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 12 }}>{p.description}</p>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {p.phases.map((phase, i) => (
                  <span
                    key={i}
                    style={{
                      fontSize: 11, padding: "2px 8px", borderRadius: 4,
                      background: "#f3f4f6", color: "#4b5563",
                    }}
                  >
                    {i + 1}. {phase}
                  </span>
                ))}
              </div>
              {benchmarks[`${p.name} (${p.srs})`] && (
                <div style={{
                  marginTop: 12, padding: 8, background: "#f0fdf4",
                  borderRadius: 8, fontSize: 12, color: "#16a34a",
                }}>
                  {benchmarks[`${p.name} (${p.srs})`].avg_latency_ms}ms avg |{" "}
                  {benchmarks[`${p.name} (${p.srs})`].ops_per_sec} ops/s
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Benchmark Button */}
      <div style={{ textAlign: "center", marginBottom: 32 }}>
        <button
          onClick={runBenchmark}
          disabled={benchmarking}
          style={{
            padding: "12px 32px", borderRadius: 8,
            background: benchmarking ? "#d1d5db" : "#4f46e5", color: "white",
            border: "none", cursor: benchmarking ? "wait" : "pointer",
            fontWeight: 600, fontSize: 15,
          }}
        >
          {benchmarking ? "Running Benchmark..." : "Run Protocol Benchmark (1000 iterations)"}
        </button>
        {Object.keys(benchmarks).length > 0 && (
          <div style={{ marginTop: 16 }}>
            <table style={{
              width: "100%", borderCollapse: "collapse",
              background: "white", borderRadius: 12, overflow: "hidden",
            }}>
              <thead>
                <tr style={{ background: "#f9fafb" }}>
                  <th style={{ padding: "10px 16px", textAlign: "left", fontSize: 13, fontWeight: 600 }}>Protocol</th>
                  <th style={{ padding: "10px 16px", textAlign: "right", fontSize: 13, fontWeight: 600 }}>Avg Latency</th>
                  <th style={{ padding: "10px 16px", textAlign: "right", fontSize: 13, fontWeight: 600 }}>Ops/sec</th>
                  <th style={{ padding: "10px 16px", textAlign: "right", fontSize: 13, fontWeight: 600 }}>Phases</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(benchmarks).map(([name, bm]) => (
                  <tr key={name} style={{ borderTop: "1px solid #e5e7eb" }}>
                    <td style={{ padding: "10px 16px", fontSize: 13 }}>{name}</td>
                    <td style={{ padding: "10px 16px", textAlign: "right", fontSize: 13, fontFamily: "monospace" }}>
                      {bm.avg_latency_ms}ms
                    </td>
                    <td style={{ padding: "10px 16px", textAlign: "right", fontSize: 13, fontFamily: "monospace" }}>
                      {bm.ops_per_sec}
                    </td>
                    <td style={{ padding: "10px 16px", textAlign: "right", fontSize: 13 }}>{bm.phases}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ABAC Test */}
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12 }}>
        ABAC Access Control Test (SRS 3)
      </h2>
      <div style={{
        background: "white", borderRadius: 12, padding: 24,
        border: "1px solid #e5e7eb", marginBottom: 16,
      }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 16 }}>
          {[
            { label: "Role", key: "user_role", options: ["viewer", "analyst", "auditor", "admin"] },
            { label: "Clearance", key: "clearance", options: ["LOW", "MEDIUM", "HIGH", "TOP_SECRET"] },
            { label: "Location", key: "location", options: ["internal", "vpn", "external"] },
            { label: "Device", key: "device_type", options: ["desktop", "mobile", "tablet"] },
            { label: "Resource Sensitivity", key: "resource_sensitivity", options: ["LOW", "MEDIUM", "HIGH", "TOP_SECRET"] },
          ].map(({ label, key, options }) => (
            <div key={key}>
              <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>
                {label}
              </label>
              <select
                value={(abacForm as Record<string, unknown>)[key] as string}
                onChange={(e) => setAbacForm({ ...abacForm, [key]: e.target.value })}
                style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: "1px solid #d1d5db" }}
              >
                {options.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          ))}
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>
              MFA Verified
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0" }}>
              <input
                type="checkbox"
                checked={abacForm.mfa_verified}
                onChange={(e) => setAbacForm({ ...abacForm, mfa_verified: e.target.checked })}
              />
              MFA Authenticated
            </label>
          </div>
        </div>
        <button
          onClick={testABAC}
          style={{
            padding: "10px 24px", borderRadius: 8,
            background: "#4f46e5", color: "white",
            border: "none", cursor: "pointer", fontWeight: 600,
          }}
        >
          Evaluate Access
        </button>
      </div>

      {abacResult && (
        <div style={{
          borderRadius: 12, padding: 20,
          background: (abacResult.allowed as boolean) ? "#f0fdf4" : "#fef2f2",
          border: `1px solid ${(abacResult.allowed as boolean) ? "#bbf7d0" : "#fecaca"}`,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
            <span style={{
              fontSize: 20, fontWeight: 700,
              color: (abacResult.allowed as boolean) ? "#16a34a" : "#dc2626",
            }}>
              {(abacResult.allowed as boolean) ? "ACCESS ALLOWED" : "ACCESS DENIED"}
            </span>
            <span style={{ fontSize: 13, color: "#6b7280" }}>
              ({(abacResult.fgac_granularity as number)} rules evaluated)
            </span>
          </div>
          <p style={{ fontSize: 14, color: "#4b5563", marginBottom: 8 }}>
            {abacResult.reason as string}
          </p>
          {(abacResult.masked_fields as string[])?.length > 0 && (
            <div style={{ fontSize: 13 }}>
              <span style={{ fontWeight: 600 }}>Masked fields: </span>
              {(abacResult.masked_fields as string[]).join(", ")}
              <span style={{ color: "#6b7280" }}> (masking: {abacResult.masking_level as string})</span>
            </div>
          )}
          <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 8 }}>
            Rules applied: {(abacResult.rules_applied as string[])?.join(", ")}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ProtocolsPage() {
  return (
    <AuthGuard>
      <NavBar />
      <ProtocolsContent />
    </AuthGuard>
  );
}

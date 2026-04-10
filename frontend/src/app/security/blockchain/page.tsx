"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/hooks/useAuth";

type AuditBlock = {
  index: number;
  timestamp: number;
  transaction_id: string;
  user_id: string;
  action: string;
  score: number;
  amount: number;
  reason: string;
  block_hash: string;
  prev_hash: string;
};

type ChainVerification = {
  valid: boolean;
  chain_length: number;
  error?: string;
};

function BlockchainAuditContent() {
  const { userId, accessToken } = useAuth();
  const [blocks, setBlocks] = useState<AuditBlock[]>([]);
  const [chainLength, setChainLength] = useState(0);
  const [verification, setVerification] = useState<ChainVerification | null>(null);
  const [searchUserId, setSearchUserId] = useState("");
  const [searchAction, setSearchAction] = useState("");
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState("");

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  };

  const fetchChain = async () => {
    setError("");
    try {
      const res = await fetch("/api/v1/security/audit/chain?limit=50", { headers });
      if (!res.ok) { setError(`Chain fetch failed: ${res.status}`); return; }
      const data = await res.json();
      setBlocks(data.blocks || []);
      setChainLength(data.chain_length || 0);
    } catch (e) {
      setError("Network error: unable to fetch chain");
    } finally {
      setLoading(false);
    }
  };

  const verifyChain = async () => {
    setVerifying(true);
    setError("");
    try {
      const res = await fetch("/api/v1/security/audit/verify", { headers });
      if (!res.ok) { setError(`Verify failed: ${res.status}`); return; }
      setVerification(await res.json());
    } catch (e) {
      setError("Network error: unable to verify chain");
    } finally {
      setVerifying(false);
    }
  };

  const searchBlocks = async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (searchUserId) params.set("user_id", searchUserId);
      if (searchAction) params.set("action", searchAction);
      const res = await fetch(`/api/v1/security/audit/search?${params}`, { headers });
      if (!res.ok) { setError(`Search failed: ${res.status}`); return; }
      const data = await res.json();
      setBlocks(data.blocks || []);
    } catch (e) {
      setError("Network error: unable to search blocks");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (accessToken) fetchChain();
  }, [accessToken]);

  const actionColor = (action: string) => {
    switch (action) {
      case "BLOCK": return "#ef4444";
      case "REVIEW": return "#f59e0b";
      case "SOFT_REVIEW": return "#3b82f6";
      case "PASS": return "#10b981";
      default: return "#6b7280";
    }
  };

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 16px" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
        Blockchain Audit Trail
      </h1>
      <p style={{ color: "#6b7280", marginBottom: 24 }}>
        SRS 1,2,3,5,6 - On-chain/Off-chain Hash Chain Audit Log
      </p>

      {/* Chain Status */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(3, 1fr)",
        gap: 16, marginBottom: 24,
      }}>
        <div style={{
          background: "#f0fdf4", borderRadius: 12, padding: 20,
          border: "1px solid #bbf7d0",
        }}>
          <div style={{ fontSize: 14, color: "#16a34a" }}>Chain Length</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{chainLength}</div>
        </div>
        <div style={{
          background: verification?.valid === false ? "#fef2f2" : "#eff6ff",
          borderRadius: 12, padding: 20,
          border: `1px solid ${verification?.valid === false ? "#fecaca" : "#bfdbfe"}`,
        }}>
          <div style={{ fontSize: 14, color: verification?.valid === false ? "#dc2626" : "#2563eb" }}>
            Integrity
          </div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>
            {verification === null ? "---" : verification.valid ? "VALID" : "BROKEN"}
          </div>
        </div>
        <div style={{ background: "#faf5ff", borderRadius: 12, padding: 20, border: "1px solid #e9d5ff" }}>
          <button
            onClick={verifyChain}
            disabled={verifying}
            style={{
              width: "100%", padding: "10px 16px", borderRadius: 8,
              background: verifying ? "#d8b4fe" : "#7c3aed", color: "white",
              border: "none", cursor: verifying ? "wait" : "pointer",
              fontWeight: 600, fontSize: 14,
            }}
          >
            {verifying ? "Verifying..." : "Verify Chain Integrity"}
          </button>
          <div style={{ fontSize: 12, color: "#7c3aed", marginTop: 8, textAlign: "center" }}>
            SHA-256 Hash + Merkle Root
          </div>
        </div>
      </div>

      {/* Search */}
      <div style={{
        display: "flex", gap: 12, marginBottom: 24,
        background: "#f9fafb", padding: 16, borderRadius: 12,
      }}>
        <input
          placeholder="User ID"
          value={searchUserId}
          onChange={(e) => setSearchUserId(e.target.value)}
          style={{
            flex: 1, padding: "8px 12px", borderRadius: 8,
            border: "1px solid #d1d5db",
          }}
        />
        <select
          value={searchAction}
          onChange={(e) => setSearchAction(e.target.value)}
          style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid #d1d5db" }}
        >
          <option value="">All Actions</option>
          <option value="PASS">PASS</option>
          <option value="SOFT_REVIEW">SOFT_REVIEW</option>
          <option value="REVIEW">REVIEW</option>
          <option value="BLOCK">BLOCK</option>
        </select>
        <button
          onClick={searchBlocks}
          style={{
            padding: "8px 20px", borderRadius: 8,
            background: "#4f46e5", color: "white",
            border: "none", cursor: "pointer", fontWeight: 600,
          }}
        >
          Search
        </button>
        <button
          onClick={fetchChain}
          style={{
            padding: "8px 20px", borderRadius: 8,
            background: "#6b7280", color: "white",
            border: "none", cursor: "pointer",
          }}
        >
          Reset
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          background: "#fef2f2", color: "#dc2626", padding: 12,
          borderRadius: 8, marginBottom: 16, fontSize: 14,
        }}>
          {error}
        </div>
      )}

      {/* Block List */}
      {loading ? (
        <p style={{ textAlign: "center", color: "#9ca3af" }}>Loading...</p>
      ) : blocks.length === 0 ? (
        <p style={{ textAlign: "center", color: "#9ca3af" }}>No audit blocks found</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {blocks.map((block) => (
            <div
              key={block.index}
              style={{
                background: "white", borderRadius: 12, padding: 16,
                border: "1px solid #e5e7eb",
                borderLeft: `4px solid ${actionColor(block.action)}`,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                  <span style={{
                    fontWeight: 700, fontSize: 14,
                    background: "#f3f4f6", padding: "2px 8px", borderRadius: 4,
                  }}>
                    #{block.index}
                  </span>
                  <span style={{
                    fontWeight: 600, fontSize: 13,
                    color: actionColor(block.action),
                    background: `${actionColor(block.action)}15`,
                    padding: "2px 10px", borderRadius: 12,
                  }}>
                    {block.action}
                  </span>
                  <span style={{ fontSize: 13, color: "#6b7280" }}>
                    {block.transaction_id}
                  </span>
                </div>
                <span style={{ fontSize: 12, color: "#9ca3af" }}>
                  {typeof block.timestamp === "number"
                    ? new Date(block.timestamp * 1000).toLocaleString("ko-KR")
                    : String(block.timestamp)
                  }
                </span>
              </div>
              <div style={{ display: "flex", gap: 24, fontSize: 13, color: "#4b5563" }}>
                <span>User: {block.user_id}</span>
                <span>Score: {block.score?.toFixed(4)}</span>
                <span>Amount: {block.amount?.toLocaleString()}</span>
              </div>
              <div style={{
                fontSize: 11, color: "#9ca3af", fontFamily: "monospace",
                marginTop: 8, wordBreak: "break-all",
              }}>
                Hash: {block.block_hash}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function BlockchainAuditPage() {
  return (
    <AuthGuard>
      <NavBar />
      <BlockchainAuditContent />
    </AuthGuard>
  );
}

"use client";

import { useState } from "react";

const EMOTIONS = [
  { value: "happy",    label: "기쁨",    emoji: "😊" },
  { value: "stressed", label: "스트레스", emoji: "😰" },
  { value: "bored",    label: "무료함",  emoji: "😐" },
  { value: "reward",   label: "보상심리", emoji: "🎁" },
  { value: "impulse",  label: "충동",    emoji: "⚡" },
  { value: "neutral",  label: "평온",    emoji: "😑" },
];

interface Props {
  userId: string;
  transactionId: string;
  transactionInfo?: string;
  existingEmotion?: string;
  onSave: (emotion: string, intensity: number) => void;
  onClose: () => void;
}

export default function EmotionTagDialog({
  userId, transactionId, transactionInfo, existingEmotion, onSave, onClose,
}: Props) {
  const [selected, setSelected] = useState(existingEmotion ?? "");
  const [intensity, setIntensity] = useState(3);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!selected) return;
    setSaving(true);
    try {
      await fetch("/api/v1/emotion/tag", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, transaction_id: transactionId, emotion: selected, intensity, note }),
      });
      onSave(selected, intensity);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 2000,
    }} onClick={onClose}>
      <div
        style={{
          background: "#fff", borderRadius: 16, padding: 28, width: 380,
          boxShadow: "0 16px 48px rgba(0,0,0,0.2)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginBottom: 4 }}>감정 태깅</h3>
        {transactionInfo && (
          <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 20 }}>{transactionInfo}</p>
        )}

        {/* 감정 선택 */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, marginBottom: 20 }}>
          {EMOTIONS.map((em) => (
            <button
              key={em.value}
              onClick={() => setSelected(em.value)}
              style={{
                padding: "12px 8px", borderRadius: 10, cursor: "pointer",
                border: selected === em.value ? "2px solid #6366f1" : "1px solid #e5e7eb",
                background: selected === em.value ? "#eef2ff" : "#fff",
                display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
              }}
            >
              <span style={{ fontSize: 24 }}>{em.emoji}</span>
              <span style={{ fontSize: 12, fontWeight: selected === em.value ? 700 : 400 }}>
                {em.label}
              </span>
            </button>
          ))}
        </div>

        {/* 강도 슬라이더 */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 13 }}>
            <span style={{ fontWeight: 600 }}>강도</span>
            <span style={{ color: "#6366f1", fontWeight: 700 }}>
              {"●".repeat(intensity)}{"○".repeat(5 - intensity)}
            </span>
          </div>
          <input
            type="range" min={1} max={5} value={intensity}
            onChange={(e) => setIntensity(Number(e.target.value))}
            style={{ width: "100%", accentColor: "#6366f1" }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#9ca3af", marginTop: 2 }}>
            <span>약함</span><span>강함</span>
          </div>
        </div>

        {/* 메모 */}
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="간단한 메모 (선택)"
          rows={2}
          style={{
            width: "100%", padding: "8px 12px", border: "1px solid #e5e7eb",
            borderRadius: 8, fontSize: 13, resize: "none", boxSizing: "border-box",
            marginBottom: 16,
          }}
        />

        {/* 버튼 */}
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={onClose}
            style={{
              flex: 1, padding: "10px", background: "#f1f5f9", border: "none",
              borderRadius: 8, cursor: "pointer", fontWeight: 600,
            }}
          >
            취소
          </button>
          <button
            onClick={handleSave}
            disabled={!selected || saving}
            style={{
              flex: 2, padding: "10px", background: "#6366f1", color: "#fff",
              border: "none", borderRadius: 8, cursor: selected ? "pointer" : "not-allowed",
              fontWeight: 700, opacity: selected ? 1 : 0.5,
            }}
          >
            {saving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}

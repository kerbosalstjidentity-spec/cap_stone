"use client";

import { useState } from "react";

interface HeatmapCell {
  category: string;
  category_kr: string;
  value: number;
  raw_avg: number;
  count: number;
}

interface HeatmapRow {
  emotion: string;
  emotion_kr: string;
  cells: HeatmapCell[];
}

interface Props {
  rows: HeatmapRow[];
}

function cellColor(value: number): string {
  if (value <= 0) return "#f8fafc";
  // 0~1 → 연보라(낮음) ~ 진보라(높음)
  const intensity = Math.round(value * 255);
  const r = Math.round(240 - value * 140);
  const g = Math.round(240 - value * 160);
  const b = 255;
  return `rgb(${r},${g},${b})`;
}

export default function EmotionHeatmap({ rows }: Props) {
  const [tooltip, setTooltip] = useState<{ row: number; col: number; cell: HeatmapCell } | null>(null);

  if (!rows || rows.length === 0) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "#9ca3af", fontSize: 14 }}>
        감정 태그 데이터가 없습니다. 거래에 감정을 태깅하면 히트맵이 표시됩니다.
      </div>
    );
  }

  const categories = rows[0]?.cells ?? [];

  return (
    <div style={{ overflowX: "auto" }}>
      <div style={{
        display: "grid",
        gridTemplateColumns: `80px repeat(${categories.length}, 1fr)`,
        gap: 2,
        minWidth: 700,
      }}>
        {/* 헤더 행 */}
        <div style={{ fontSize: 10, color: "#9ca3af", padding: "4px 2px" }} />
        {categories.map((cell) => (
          <div key={cell.category} style={{
            fontSize: 10, color: "#6b7280", textAlign: "center",
            padding: "4px 2px", fontWeight: 600,
          }}>
            {cell.category_kr}
          </div>
        ))}

        {/* 데이터 행 */}
        {rows.map((row, ri) => (
          <>
            <div key={`label-${ri}`} style={{
              fontSize: 12, fontWeight: 600, padding: "8px 4px",
              display: "flex", alignItems: "center",
              color: "#374151",
            }}>
              {row.emotion_kr}
            </div>
            {row.cells.map((cell, ci) => (
              <div
                key={`${ri}-${ci}`}
                onMouseEnter={() => setTooltip({ row: ri, col: ci, cell })}
                onMouseLeave={() => setTooltip(null)}
                style={{
                  height: 40,
                  background: cellColor(cell.value),
                  borderRadius: 4,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 10, color: cell.value > 0.6 ? "#fff" : "#6b7280",
                  cursor: cell.count > 0 ? "pointer" : "default",
                  position: "relative",
                  border: tooltip?.row === ri && tooltip?.col === ci ? "2px solid #6366f1" : "2px solid transparent",
                  transition: "border-color 0.15s",
                }}
              >
                {cell.count > 0 ? cell.count : ""}
                {tooltip?.row === ri && tooltip?.col === ci && cell.count > 0 && (
                  <div style={{
                    position: "absolute", bottom: "calc(100% + 6px)", left: "50%",
                    transform: "translateX(-50%)",
                    background: "#1e293b", color: "#fff", borderRadius: 6,
                    padding: "6px 10px", fontSize: 11, whiteSpace: "nowrap",
                    zIndex: 10, pointerEvents: "none",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
                  }}>
                    {row.emotion_kr} × {cell.category_kr}<br />
                    평균 {cell.raw_avg.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}원 ({cell.count}건)
                  </div>
                )}
              </div>
            ))}
          </>
        ))}
      </div>

      {/* 범례 */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, fontSize: 11, color: "#6b7280" }}>
        <span>낮음</span>
        <div style={{
          width: 120, height: 10, borderRadius: 5,
          background: "linear-gradient(to right, #f8fafc, #6366f1)",
        }} />
        <span>높음 (거래 평균 대비)</span>
        <span style={{ marginLeft: 12, color: "#9ca3af" }}>셀 숫자 = 거래 건수</span>
      </div>
    </div>
  );
}

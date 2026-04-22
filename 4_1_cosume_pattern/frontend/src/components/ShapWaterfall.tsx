"use client";

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Cell, ReferenceLine, ResponsiveContainer,
} from "recharts";

interface ShapFeature {
  feature: string;
  feature_kr: string;
  shap_value: number;
  value: number;
}

interface Props {
  features: ShapFeature[];
  baseValue?: number;
  prediction?: number;
}

export default function ShapWaterfall({ features, baseValue = 0.5, prediction = 0 }: Props) {
  const sorted = [...features].sort((a, b) => Math.abs(b.shap_value) - Math.abs(a.shap_value));

  const data = sorted.map((f) => ({
    name: f.feature_kr,
    value: f.shap_value,
    absValue: Math.abs(f.shap_value),
    raw: f.value,
    positive: f.shap_value > 0,
  }));

  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.[0]) return null;
    const d = payload[0].payload;
    return (
      <div style={{
        background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8,
        padding: "10px 14px", fontSize: 13, boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
      }}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>{d.name}</div>
        <div style={{ color: d.positive ? "#ef4444" : "#3b82f6" }}>
          SHAP: {d.value > 0 ? "+" : ""}{d.value.toFixed(4)}
        </div>
        <div style={{ color: "#6b7280" }}>실제값: {d.raw.toFixed(3)}</div>
      </div>
    );
  };

  return (
    <div>
      <div style={{
        display: "flex", gap: 16, marginBottom: 12, fontSize: 12, color: "#6b7280",
      }}>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 12, height: 12, background: "#ef4444", borderRadius: 2, display: "inline-block" }} />
          위험 증가 요인
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 12, height: 12, background: "#3b82f6", borderRadius: 2, display: "inline-block" }} />
          위험 감소 요인
        </span>
        <span style={{ marginLeft: "auto" }}>
          기준값: {(baseValue * 100).toFixed(0)}% → 예측: {(prediction * 100).toFixed(0)}%
        </span>
      </div>

      <ResponsiveContainer width="100%" height={data.length * 40 + 60}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 40, top: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tickFormatter={(v) => v.toFixed(2)} fontSize={11} />
          <YAxis type="category" dataKey="name" width={90} fontSize={12} />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine x={0} stroke="#374151" strokeWidth={1} />
          <Bar dataKey="value" radius={[0, 4, 4, 0]}>
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.positive ? "#ef4444" : "#3b82f6"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

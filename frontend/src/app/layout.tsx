import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "소비 패턴 분석",
  description: "AI 기반 지능형 소비 패턴 분석 & 데이터 기반 소비 전략 제안",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}

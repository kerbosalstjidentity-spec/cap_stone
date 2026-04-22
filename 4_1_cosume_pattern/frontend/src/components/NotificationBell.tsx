"use client";

import { useEffect, useRef } from "react";
import { useNotifications, getEventIcon } from "@/hooks/useNotifications";
import NotificationPanel from "./NotificationPanel";

export default function NotificationBell() {
  const {
    unreadCount, isOpen, togglePanel, closePanel,
    notifications, markAsRead, markAllRead,
  } = useNotifications();

  const containerRef = useRef<HTMLDivElement>(null);

  // 패널 외부 클릭 시 닫기
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        closePanel();
      }
    }
    if (isOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isOpen, closePanel]);

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      {/* 벨 버튼 */}
      <button
        onClick={togglePanel}
        title="알림"
        style={{
          position: "relative",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          padding: "4px 6px",
          fontSize: 20,
          lineHeight: 1,
          color: isOpen ? "var(--primary)" : "var(--text-secondary)",
        }}
      >
        🔔
        {unreadCount > 0 && (
          <span style={{
            position: "absolute",
            top: 0, right: 0,
            background: "#ef4444",
            color: "#fff",
            borderRadius: "50%",
            fontSize: 10,
            fontWeight: 700,
            minWidth: 16,
            height: 16,
            lineHeight: "16px",
            textAlign: "center",
            padding: "0 3px",
          }}>
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {/* 알림 패널 드롭다운 */}
      {isOpen && (
        <NotificationPanel
          notifications={notifications}
          onMarkAsRead={markAsRead}
          onMarkAllRead={markAllRead}
          onClose={closePanel}
          getEventIcon={getEventIcon}
        />
      )}
    </div>
  );
}

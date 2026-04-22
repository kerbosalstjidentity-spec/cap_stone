"use client";

import { NotificationItem } from "@/hooks/useNotifications";

function timeAgo(dateStr: string): string {
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
  if (diff < 60) return "방금 전";
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  return `${Math.floor(diff / 86400)}일 전`;
}

interface Props {
  notifications: NotificationItem[];
  onMarkAsRead: (id: number) => void;
  onMarkAllRead: () => void;
  onClose: () => void;
  getEventIcon: (type: string) => string;
}

export default function NotificationPanel({
  notifications, onMarkAsRead, onMarkAllRead, onClose, getEventIcon,
}: Props) {
  const unread = notifications.filter((n) => !n.is_read).length;

  return (
    <div style={{
      position: "absolute",
      top: "calc(100% + 8px)",
      right: 0,
      width: 340,
      maxHeight: 480,
      background: "#fff",
      border: "1px solid var(--border)",
      borderRadius: 12,
      boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
      zIndex: 1000,
      display: "flex",
      flexDirection: "column",
    }}>
      {/* 헤더 */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "12px 16px",
        borderBottom: "1px solid var(--border)",
      }}>
        <span style={{ fontWeight: 700, fontSize: 15 }}>
          알림 {unread > 0 && <span style={{ color: "#ef4444" }}>({unread})</span>}
        </span>
        {unread > 0 && (
          <button
            onClick={onMarkAllRead}
            style={{
              background: "transparent", border: "none", cursor: "pointer",
              fontSize: 12, color: "var(--primary)", fontWeight: 600,
            }}
          >
            모두 읽음
          </button>
        )}
      </div>

      {/* 목록 */}
      <div style={{ overflowY: "auto", flex: 1 }}>
        {notifications.length === 0 ? (
          <div style={{ padding: "32px 16px", textAlign: "center", color: "var(--text-secondary)", fontSize: 14 }}>
            알림이 없습니다.
          </div>
        ) : (
          notifications.map((n) => (
            <div
              key={n.id}
              onClick={() => { if (!n.is_read) onMarkAsRead(n.id); }}
              style={{
                display: "flex", gap: 10, padding: "12px 16px",
                borderBottom: "1px solid #f1f5f9",
                background: n.is_read ? "#fff" : "#f0f5ff",
                cursor: n.is_read ? "default" : "pointer",
                transition: "background 0.15s",
              }}
            >
              <span style={{ fontSize: 18, flexShrink: 0, lineHeight: 1.4 }}>
                {getEventIcon(n.event_type)}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 13, fontWeight: n.is_read ? 400 : 700,
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                }}>
                  {n.title}
                </div>
                {n.body && (
                  <div style={{
                    fontSize: 12, color: "var(--text-secondary)", marginTop: 2,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>
                    {n.body}
                  </div>
                )}
                <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>
                  {timeAgo(n.created_at)}
                </div>
              </div>
              {!n.is_read && (
                <div style={{
                  width: 8, height: 8, borderRadius: "50%", background: "#6366f1",
                  flexShrink: 0, marginTop: 6,
                }} />
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

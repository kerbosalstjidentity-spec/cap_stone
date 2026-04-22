"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "./useAuth";
import { useWebSocket } from "./useWebSocket";

export interface NotificationItem {
  id: number;
  event_type: string;
  title: string;
  body: string;
  metadata_json: string;
  is_read: boolean;
  created_at: string;
}

const EVENT_ICONS: Record<string, string> = {
  budget_warning: "⚠️",
  anomaly_detected: "🚨",
  challenge_completed: "🏆",
  badge_earned: "🎖️",
  emotion_risk: "💭",
  xai_insight: "🧠",
  daily_summary: "📊",
};

export function getEventIcon(event_type: string): string {
  return EVENT_ICONS[event_type] ?? "🔔";
}

export function useNotifications() {
  const { userId, isLoggedIn } = useAuth();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isOpen, setIsOpen] = useState(false);
  const fetchedRef = useRef(false);

  const fetchNotifications = useCallback(async () => {
    if (!userId) return;
    try {
      const res = await fetch(`/api/v1/notifications/?user_id=${userId}&limit=30`);
      if (!res.ok) return;
      const data = await res.json();
      setNotifications(data.notifications ?? []);
      setUnreadCount(data.unread_count ?? 0);
    } catch {
      // Redis/backend unavailable — silent fail
    }
  }, [userId]);

  // 초기 로드
  useEffect(() => {
    if (isLoggedIn && userId && !fetchedRef.current) {
      fetchedRef.current = true;
      fetchNotifications();
    }
  }, [isLoggedIn, userId, fetchNotifications]);

  // WebSocket 실시간 수신
  useWebSocket({
    onMessage: (data) => {
      const notif = data as NotificationItem;
      if (!notif?.id) return;
      setNotifications((prev) => [notif, ...prev.slice(0, 49)]);
      setUnreadCount((c) => c + 1);
    },
  });

  const markAsRead = useCallback(async (id: number) => {
    if (!userId) return;
    await fetch(`/api/v1/notifications/${id}/read?user_id=${userId}`, { method: "PUT" });
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
    );
    setUnreadCount((c) => Math.max(0, c - 1));
  }, [userId]);

  const markAllRead = useCallback(async () => {
    if (!userId) return;
    await fetch(`/api/v1/notifications/read-all?user_id=${userId}`, { method: "PUT" });
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
  }, [userId]);

  const togglePanel = useCallback(() => setIsOpen((v) => !v), []);
  const closePanel = useCallback(() => setIsOpen(false), []);

  return {
    notifications,
    unreadCount,
    isOpen,
    togglePanel,
    closePanel,
    markAsRead,
    markAllRead,
    refresh: fetchNotifications,
  };
}

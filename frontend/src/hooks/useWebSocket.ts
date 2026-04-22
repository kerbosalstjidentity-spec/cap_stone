"use client";

import { useEffect, useRef, useState } from "react";

interface UseWebSocketOptions {
  onMessage?: (data: unknown) => void;
}

export function useWebSocket({ onMessage }: UseWebSocketOptions = {}) {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retryDelay = useRef(1000);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmounted = useRef(false);

  useEffect(() => {
    unmounted.current = false;

    function connect() {
      const token = localStorage.getItem("access_token");
      if (!token) return;

      // Next.js rewrites don't handle WebSocket — connect directly to backend
      const ws = new WebSocket(`ws://localhost:8020/v1/notifications/ws?token=${token}`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (unmounted.current) return;
        setIsConnected(true);
        retryDelay.current = 1000; // 성공 시 딜레이 리셋
      };

      ws.onmessage = (event) => {
        if (unmounted.current) return;
        try {
          const data = JSON.parse(event.data);
          onMessage?.(data);
        } catch {
          // non-JSON (e.g. "pong") — 무시
        }
      };

      ws.onclose = () => {
        if (unmounted.current) return;
        setIsConnected(false);
        // 지수 백오프 재접속 (최대 30초)
        retryTimer.current = setTimeout(() => {
          if (!unmounted.current) {
            retryDelay.current = Math.min(retryDelay.current * 2, 30000);
            connect();
          }
        }, retryDelay.current);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    // ping 주기 전송 (연결 유지)
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send("ping");
      }
    }, 25000);

    return () => {
      unmounted.current = true;
      clearInterval(pingInterval);
      if (retryTimer.current) clearTimeout(retryTimer.current);
      wsRef.current?.close();
    };
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  return { isConnected };
}

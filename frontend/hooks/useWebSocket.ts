"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { getMigrationStreamUrl } from "@/services/api";

/** Message shape sent by the backend WebSocket stream */
export interface StreamEvent {
  type: string;
  timestamp: string;
  stage?: string;
  status?: string;
  message?: string;
  /** Alternative field names the backend may use */
  state?: string;
  details?: string;
  progress_percentage?: number;
  level?: string;
  content?: string;
  agent?: string;
  action?: string;
  summary?: string;
}

export type ConnectionState = "connecting" | "open" | "closed" | "error";

interface UseWebSocketOptions {
  /** Called for every parsed message received from the server */
  onMessage: (event: StreamEvent) => void;
  /** Maximum number of automatic reconnect attempts (default 5) */
  maxRetries?: number;
  /** Base reconnect delay in ms, doubles each attempt (default 2000) */
  baseDelay?: number;
}

/**
 * useWebSocket — connects to the HIPForge migration stream WebSocket.
 *
 * Features:
 * - Auto-connects on mount.
 * - Parses JSON messages and delegates to onMessage callback.
 * - Reconnects automatically on disconnect (up to maxRetries).
 * - Stops reconnecting once the migration reaches a terminal state (COMPLETED/FAILED).
 * - Cleans up the socket on unmount.
 *
 * @param migrationId - The migration UUID to stream.
 * @param options - Configuration options.
 * @returns connectionState — current WebSocket connection state.
 */
export function useWebSocket(
  migrationId: string,
  options: UseWebSocketOptions
): { connectionState: ConnectionState } {
  const { onMessage, maxRetries = 5, baseDelay = 2000 } = options;

  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMountedRef = useRef(true);
  const isTerminalRef = useRef(false);
  const onMessageRef = useRef(onMessage);

  const [connectionState, setConnectionState] =
    useState<ConnectionState>("connecting");

  // Keep onMessage ref current so the socket closure is stable
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback(() => {
    if (!isMountedRef.current || isTerminalRef.current) return;

    const url = getMigrationStreamUrl(migrationId);
    const ws = new WebSocket(url);
    wsRef.current = ws;
    setConnectionState("connecting");

    ws.onopen = () => {
      if (!isMountedRef.current) return;
      retryCountRef.current = 0;
      setConnectionState("open");
    };

    ws.onmessage = (ev: MessageEvent) => {
      if (!isMountedRef.current) return;
      try {
        const parsed: StreamEvent = JSON.parse(ev.data as string);
        // Mark terminal so we stop reconnecting
        const stage = parsed.stage ?? parsed.state ?? "";
        if (stage === "COMPLETED" || stage === "FAILED") {
          isTerminalRef.current = true;
        }
        onMessageRef.current(parsed);
      } catch {
        // Ignore malformed frames
      }
    };

    ws.onerror = () => {
      if (!isMountedRef.current) return;
      setConnectionState("error");
    };

    ws.onclose = () => {
      if (!isMountedRef.current) return;
      setConnectionState("closed");
      wsRef.current = null;

      // Don't reconnect if terminal or max retries reached
      if (
        isTerminalRef.current ||
        retryCountRef.current >= maxRetries
      ) {
        return;
      }

      const delay = baseDelay * Math.pow(2, retryCountRef.current);
      retryCountRef.current += 1;

      retryTimerRef.current = setTimeout(() => {
        if (isMountedRef.current && !isTerminalRef.current) {
          connect();
        }
      }, delay);
    };
  }, [migrationId, maxRetries, baseDelay]);

  useEffect(() => {
    isMountedRef.current = true;
    isTerminalRef.current = false;
    retryCountRef.current = 0;
    connect();

    return () => {
      isMountedRef.current = false;
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on intentional close
        wsRef.current.close();
        wsRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [migrationId]);

  return { connectionState };
}

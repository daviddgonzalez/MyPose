"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import WebcamCapture from "./WebcamCapture";
import { PKEWebSocket } from "@/lib/ws";
import type { WSIncomingMessage } from "@/lib/types";


interface LiveSessionProps {
  exerciseName?: string;
}

interface SessionLog {
  time: string;
  type: "ack" | "result" | "info" | "error";
  message: string;
}

export default function LiveSession({ exerciseName }: LiveSessionProps) {
  const [isStreaming, setIsStreaming] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [logs, setLogs] = useState<SessionLog[]>([]);
  const [framesStreamed, setFramesStreamed] = useState(0);
  const wsRef = useRef<PKEWebSocket | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  // Play/pause demo video when session starts/stops
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (isStreaming) {
      video.play().catch(() => {});
    } else {
      video.pause();
      video.currentTime = 0;
    }
  }, [isStreaming]);

  const addLog = useCallback((type: SessionLog["type"], message: string) => {
    setLogs((prev) => [
      ...prev.slice(-50), // Keep last 50 logs
      { time: new Date().toLocaleTimeString(), type, message },
    ]);
  }, []);

  // (Removed) Scroll logs to bottom automatically

  const handleMessage = useCallback(
    (message: WSIncomingMessage) => {
      switch (message.type) {
        case "ack":
          addLog("ack", `Server acknowledged ${message.frames_received} frames`);
          break;
        case "result":
          addLog(
            "result",
            `Rep ${message.rep_idx}: ${message.passed ? " Good form" : " Form deviation"} (distance: ${message.distance.toFixed(3)})`
          );
          break;
        case "session_end":
          addLog("info", `Session ended. Total frames: ${message.total_frames}`);
          setIsStreaming(false);
          break;
      }
    },
    [addLog]
  );

  const startSession = useCallback(() => {
    const ws = new PKEWebSocket({
      onOpen: () => {
        setIsConnected(true);
        setIsStreaming(true);
        setFramesStreamed(0);
        addLog("info", "Connected to stream server");
      },
      onMessage: handleMessage,
      onError: () => addLog("error", "WebSocket connection error"),
      onClose: () => {
        setIsConnected(false);
        addLog("info", "Disconnected from stream server");
      },
    });

    ws.connect();
    wsRef.current = ws;
  }, [addLog, handleMessage]);

  const stopSession = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.endSession();
      setTimeout(() => {
        wsRef.current?.disconnect();
        wsRef.current = null;
        setIsStreaming(false);
        setIsConnected(false);
      }, 500);
    }
  }, []);

  const handleLandmarks = useCallback(
    (landmarks: { x: number; y: number; z: number }[]) => {
      if (!isStreaming || !wsRef.current) return;

      const formatted = landmarks.map((lm) => [lm.x, lm.y, lm.z]);
      wsRef.current.sendFrame(formatted);
      setFramesStreamed((prev) => prev + 1);
    },
    [isStreaming]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.disconnect();
      }
    };
  }, []);

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-[var(--pke-text-primary)]">
            Live Session
            {exerciseName && (
              <span className="ml-2 text-[var(--pke-accent)]">
                — {exerciseName}
              </span>
            )}
          </h2>
          <p className="text-sm text-[var(--pke-text-secondary)] mt-0.5">
            Stream your movements in real-time for instant feedback
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Stats */}
          {isStreaming && (
            <div className="flex items-center gap-4 text-xs text-[var(--pke-text-muted)]">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-[var(--pke-danger)] animate-pulse" />
                LIVE
              </span>
              <span>{framesStreamed} frames</span>
            </div>
          )}

          <button
            onClick={isStreaming ? stopSession : startSession}
            className={`pke-btn pke-btn-sm ${
              isStreaming ? "pke-btn-danger" : "pke-btn-primary"
            }`}
          >
            {isStreaming ? "⏹ Stop" : "▶ Start Streaming"}
          </button>
        </div>
      </div>

      {/* Main Content Row: Demo Video & Camera Side by Side */}
      <div className="flex flex-row gap-6 items-start w-full">
        {/* Demo Video (Left) */}
        <div className="flex-1 min-w-0">
          <div className="pke-card p-4 h-full flex flex-col items-center justify-center">
            <h3 className="text-sm font-medium text-[var(--pke-text-primary)] mb-2">
              Example — Correct Squat Form
            </h3>
            <video
              ref={videoRef}
              src="/examples/squat.mp4"
              controls
              loop
              muted
              playsInline
              className="w-full max-w-md rounded-lg"
            />
          </div>
        </div>
        {/* Camera Panel (Right) */}
        <div className="flex-1 min-w-0 flex justify-center">
          <div className="shrink-0 flex justify-center bg-white border border-[#e2e8f0] rounded-sm p-1.5 shadow-sm">
            <WebcamCapture
              onLandmarks={handleLandmarks}
              active={isStreaming}
              width={640}
              height={480}
            />
          </div>
        </div>
      </div>

      {/* Session Log at Bottom */}
      <div className="session-log-panel mt-6">
        <div className="border border-[#e2e8f0] bg-white flex flex-col h-[200px] w-full min-w-0 shadow-sm">
          <div className="px-6 py-4 border-b border-[#e2e8f0] flex items-center justify-between">
            <h3 className="text-sm font-bold uppercase tracking-widest text-[#0f172a]">
              Session Log
            </h3>
            <div className="flex items-center gap-1.5">
              <span
                className={`w-2 h-2 rounded-full ${
                  isConnected
                    ? "bg-[var(--pke-success)]"
                    : "bg-[var(--pke-text-muted)]"
                }`}
              />
              <span className="text-[11px] text-[var(--pke-text-muted)]">
                {isConnected ? "Connected" : "Disconnected"}
              </span>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-1.5 font-mono text-xs">
            {logs.length === 0 ? (
              <p className="text-[var(--pke-text-muted)] text-center py-8">
                Session logs will appear here…
              </p>
            ) : (
              logs.map((log, i) => (
                <div key={i} className="flex gap-2">
                  <span className="text-[var(--pke-text-muted)] shrink-0">
                    {log.time}
                  </span>
                  <span
                    className={
                      log.type === "error"
                        ? "text-[var(--pke-danger)]"
                        : log.type === "result"
                        ? "text-[var(--pke-success)]"
                        : log.type === "ack"
                        ? "text-[var(--pke-accent)]"
                        : "text-[var(--pke-text-secondary)]"
                    }
                  >
                    {log.message}
                  </span>
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}

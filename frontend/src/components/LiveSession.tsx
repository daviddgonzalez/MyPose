"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import WebcamCapture from "./WebcamCapture";
import { PKEWebSocket } from "@/lib/ws";
import type { WSIncomingMessage, WSFeedbackMessage, StrictnessLevel } from "@/lib/types";


interface LiveSessionProps {
  exerciseName?: string;
}

interface SessionLog {
  time: string;
  type: "ack" | "result" | "info" | "error" | "feedback";
  message: string;
}

export default function LiveSession({ exerciseName }: LiveSessionProps) {
  const [isStreaming, setIsStreaming] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [logs, setLogs] = useState<SessionLog[]>([]);
  const [framesStreamed, setFramesStreamed] = useState(0);
  const [strictness, setStrictness] = useState<StrictnessLevel>("moderate");
  const [sessionFeedback, setSessionFeedback] =
    useState<WSFeedbackMessage | null>(null);
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
        case "session_feedback":
          setSessionFeedback(message);
          addLog(
            "feedback",
            `Analysis complete — Score: ${message.overall_score}/100 | ${message.message}`
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
    setSessionFeedback(null); // Clear previous feedback
    const ws = new PKEWebSocket({
      onOpen: () => {
        setIsConnected(true);
        setIsStreaming(true);
        setFramesStreamed(0);
        addLog("info", "Connected to stream server");
        ws.sendConfig(strictness, exerciseName || "squat");
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
      addLog("info", "Ending session — analyzing movement…");
      wsRef.current.endSession();
      setTimeout(() => {
        wsRef.current?.disconnect();
        wsRef.current = null;
        setIsStreaming(false);
        setIsConnected(false);
      }, 3000); // Give backend time to analyze and respond
    }
  }, [addLog]);

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

          {/* Strictness Selector */}
          <div className="mt-3 flex items-center bg-[#f8fafc] border border-[#e2e8f0] rounded-lg p-1 w-fit">
            {(
              [
                { value: "lenient", label: "🟢 Lenient" },
                { value: "moderate", label: "🔵 Moderate" },
                { value: "strict", label: "🟠 Strict" },
                { value: "drill_sergeant", label: "🔴 Drill Sgt" },
              ] as const
            ).map((opt) => (
              <button
                key={opt.value}
                onClick={() => setStrictness(opt.value)}
                disabled={isStreaming}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                  strictness === opt.value
                    ? "bg-white text-[#0f172a] shadow-sm ring-1 ring-slate-900/5"
                    : "text-[#64748b] hover:text-[#0f172a]"
                } ${isStreaming ? "opacity-50 cursor-not-allowed" : ""}`}
              >
                {opt.label}
              </button>
            ))}
          </div>
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
            {isStreaming ? "Stop" : "Start Streaming"}
          </button>
        </div>
      </div>

      {/* Main Content Row: Demo Video & Camera Side by Side */}
      <div className="grid grid-cols-2 gap-6 w-full" style={{ height: 480 }}>
        {/* Demo Video (Left) */}
        <div className="border border-[#e2e8f0] overflow-hidden bg-[#0f172a] h-full">
          <video
            ref={videoRef}
            src="/examples/squat.mp4"
            controls
            loop
            muted
            playsInline
            className="w-full h-full object-cover"
          />
        </div>
        {/* Camera Panel (Right) */}
        <div className="h-full">
          <WebcamCapture
            onLandmarks={handleLandmarks}
            active={isStreaming}
            width={640}
            height={480}
          />
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
                        : log.type === "feedback"
                        ? "text-[#6366f1] font-semibold"
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

      {/* ── Session Feedback Card ────────────────────────────────── */}
      {sessionFeedback && (
        <div className="border border-[#e2e8f0] bg-white shadow-sm animate-fade-in">
          {/* Feedback Header */}
          <div className="px-6 py-4 border-b border-[#e2e8f0] flex items-center justify-between">
            <h3 className="text-sm font-bold uppercase tracking-widest text-[#0f172a]">
              Session Feedback
            </h3>
            <div className="flex items-center gap-3">
              <span className="text-[11px] text-[var(--pke-text-muted)]">
                {sessionFeedback.total_frames} frames •{" "}
                {sessionFeedback.duration_seconds}s
              </span>
              {/* ML-READY: Show calibration badge when available */}
              {sessionFeedback.calibration_available ? (
                <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest bg-[#6366f1]/10 text-[#6366f1]">
                  Calibrated
                </span>
              ) : (
                <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest bg-[#f59e0b]/10 text-[#f59e0b]">
                  Baseline
                </span>
              )}
              <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest bg-slate-100 text-slate-600 border border-slate-200 ml-2">
                {sessionFeedback.strictness_level}
              </span>
            </div>
          </div>

          {/* Score + Summary */}
          <div className="px-6 py-5">
            <div className="flex items-center gap-6 mb-5">
              {/* Score Circle */}
              <div className="relative w-20 h-20 shrink-0">
                <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                  <path
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none"
                    stroke="#e2e8f0"
                    strokeWidth="3"
                  />
                  <path
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none"
                    stroke={
                      sessionFeedback.overall_score >= 80
                        ? "#10b981"
                        : sessionFeedback.overall_score >= 60
                        ? "#6366f1"
                        : sessionFeedback.overall_score >= 40
                        ? "#f59e0b"
                        : "#ef4444"
                    }
                    strokeWidth="3"
                    strokeDasharray={`${sessionFeedback.overall_score}, 100`}
                    strokeLinecap="round"
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-lg font-extrabold text-[#0f172a]">
                    {Math.round(sessionFeedback.overall_score)}
                  </span>
                </div>
              </div>

              <div className="min-w-0">
                <p className="text-sm text-[#475569] leading-relaxed">
                  {sessionFeedback.message}
                </p>

                {/* ML-READY: Show pass/fail when calibration is available */}
                {sessionFeedback.calibration_available &&
                  sessionFeedback.passed !== null &&
                  sessionFeedback.passed !== undefined && (
                    <div className="mt-2 flex items-center gap-2">
                      <span
                        className={`px-3 py-1 text-[10px] font-bold uppercase tracking-widest ${
                          sessionFeedback.passed
                            ? "bg-[#10b981]/10 text-[#10b981]"
                            : "bg-[#ef4444]/10 text-[#ef4444]"
                        }`}
                      >
                        {sessionFeedback.passed ? "Passed" : "Deviation Detected"}
                      </span>
                      {sessionFeedback.distance_to_centroid != null && (
                        <span className="text-[11px] text-[var(--pke-text-muted)]">
                          Distance: {sessionFeedback.distance_to_centroid.toFixed(4)}
                        </span>
                      )}
                    </div>
                  )}
              </div>
            </div>

            {/* Joint Breakdown */}
            {sessionFeedback.joint_summaries.length > 0 && (
              <div>
                <h4 className="text-[10px] font-extrabold text-[#94a3b8] uppercase tracking-widest mb-3">
                  Joint Breakdown
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {sessionFeedback.joint_summaries.map((joint) => (
                    <div
                      key={joint.joint_name}
                      className={`flex items-center justify-between px-4 py-2.5 bg-[#f8fafc] border rounded-sm ${
                        joint.passed ? "border-[#e2e8f0]" : "border-[#ef4444]"
                      }`}
                    >
                      <div>
                        <p className="text-xs font-bold flex items-center gap-1">
                          {!joint.passed && <span className="text-red-500 text-[10px] font-black">!</span>}
                          <span className={joint.passed ? "text-[#0f172a]" : "text-[#ef4444]"}>
                            {joint.joint_name}
                          </span>
                        </p>
                        <p className="text-[11px] text-[#64748b]">
                          Avg {joint.mean_angle_degrees}° • Range{" "}
                          {joint.range_of_motion_degrees}°
                        </p>
                        {!joint.passed && joint.issues?.length > 0 && (
                          <p className="text-[10px] text-[#ef4444] mt-0.5">
                            {joint.issues[0]}
                          </p>
                        )}
                      </div>
                      <div className="text-right">
                        <div className="flex items-center gap-1.5">
                          <div className="w-12 h-1.5 bg-[#e2e8f0] rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full transition-all duration-500"
                              style={{
                                width: `${joint.stability_score * 100}%`,
                                backgroundColor: joint.passed
                                  ? joint.stability_score >= 0.7
                                    ? "#10b981"
                                    : "#f59e0b"
                                  : "#ef4444",
                              }}
                            />
                          </div>
                          <span className="text-[10px] font-bold text-[#94a3b8] w-8 text-right">
                            {Math.round(joint.stability_score * 100)}%
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

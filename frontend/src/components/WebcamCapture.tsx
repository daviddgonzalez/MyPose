"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMediaPipe } from "@/hooks/useMediaPipe";
import PoseOverlay from "./PoseOverlay";

interface WebcamCaptureProps {
  /** Called each frame with extracted landmarks (33 items). */
  onLandmarks?: (
    landmarks: { x: number; y: number; z: number }[]
  ) => void;
  /** Whether to actively process frames. */
  active?: boolean;
  /** Width of the video feed. */
  width?: number;
  /** Height of the video feed. */
  height?: number;
}

export default function WebcamCapture({
  onLandmarks,
  active = true,
  width = 640,
  height = 480,
}: WebcamCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const animFrameRef = useRef<number | null>(null);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [currentLandmarks, setCurrentLandmarks] = useState<
    { x: number; y: number; z: number }[] | null
  >(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");

  const { isLoading, isReady, error: mpError, detectPose } = useMediaPipe();

  // Start camera
  useEffect(() => {
    let stream: MediaStream | null = null;
    let isMounted = true;

    async function startCamera() {
      try {
        setCameraError(null);
        setCameraReady(false);
        
        const constraints: MediaStreamConstraints = {
          video: {
            width: { ideal: width },
            height: { ideal: height },
            ...(selectedDeviceId ? { deviceId: { exact: selectedDeviceId } } : { facingMode: "user" })
          },
        };

        stream = await navigator.mediaDevices.getUserMedia(constraints);

        if (!isMounted) return;

        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          // Wait for the stream to be ready before playing
          await new Promise<void>((resolve) => {
            if (!videoRef.current) return resolve();
            videoRef.current.onloadedmetadata = () => resolve();
          });
          try {
            await videoRef.current.play();
            setCameraReady(true);
            
            // Fetch devices now that we have permission
            const allDevices = await navigator.mediaDevices.enumerateDevices();
            const videoInputs = allDevices.filter(d => d.kind === "videoinput");
            setDevices(videoInputs);
            
            // Set active device if none selected explicitly yet
            if (!selectedDeviceId && videoInputs.length > 0) {
              const activeTrack = stream.getVideoTracks()[0];
              const activeDevice = videoInputs.find(d => d.label === activeTrack.label);
              if (activeDevice) {
                setSelectedDeviceId(activeDevice.deviceId);
              }
            }
          } catch (e) {
            // Ignore AbortError — happens when component remounts quickly
            if (e instanceof DOMException && e.name === "AbortError") return;
            throw e;
          }
        }
      } catch (err) {
        if (!isMounted) return;
        const msg = err instanceof Error ? err.message : "Camera access denied";
        
        let errorHint = msg;
        if (msg.toLowerCase().includes("allocate") || msg.toLowerCase().includes("readable")) {
          errorHint = msg + " (Check if another app like Zoom or OBS is locking the camera)";
        }
        setCameraError(errorHint);
        setCameraReady(false);
        
        // Still try to enumerate devices to let user pick a different one
        try {
          const allDevices = await navigator.mediaDevices.enumerateDevices();
          const videoInputs = allDevices.filter(d => d.kind === "videoinput");
          if (videoInputs.length > 0) setDevices(videoInputs);
        } catch (e) {
          // ignore enumeration errors if already denied
        }
      }
    }

    startCamera();

    return () => {
      isMounted = false;
      if (stream) {
        stream.getTracks().forEach((t) => t.stop());
      }
    };
  }, [width, height, selectedDeviceId]);

  // Frame processing loop
  const processFrame = useCallback(() => {
    if (!active || !cameraReady || !isReady || !videoRef.current) {
      animFrameRef.current = requestAnimationFrame(processFrame);
      return;
    }

    const landmarks = detectPose(videoRef.current);
    if (landmarks) {
      const simplified = landmarks.map((lm) => ({
        x: lm.x,
        y: lm.y,
        z: lm.z,
      }));
      setCurrentLandmarks(simplified);
      onLandmarks?.(simplified);
    }

    animFrameRef.current = requestAnimationFrame(processFrame);
  }, [active, cameraReady, isReady, detectPose, onLandmarks]);

  useEffect(() => {
    animFrameRef.current = requestAnimationFrame(processFrame);
    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [processFrame]);

  // Clear skeleton when not active
  useEffect(() => {
    if (!active) {
      setCurrentLandmarks(null);
    }
  }, [active]);

  return (
    <div className="relative h-full">
      {/* Status Bar — overlaid at top-left */}
      <div className="absolute top-2 left-2 z-20 flex items-center gap-3 text-[10px] bg-black/50 px-2 py-1 rounded">
        <div className="flex items-center gap-1">
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              cameraReady ? "bg-[var(--pke-success)]" : "bg-[var(--pke-text-muted)]"
            }`}
          />
          <span className="text-white/80">
            {cameraReady ? "Camera Active" : "Connecting…"}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              isReady
                ? "bg-[var(--pke-success)]"
                : isLoading
                ? "bg-[var(--pke-warning)]"
                : "bg-[var(--pke-text-muted)]"
            }`}
          />
          <span className="text-white/80">
            {isReady
              ? "MediaPipe Ready"
              : isLoading
              ? "Loading Model…"
              : "MediaPipe Idle"}
          </span>
        </div>
      </div>

      {/* Device selector — overlaid at top-right */}
      {devices.length > 1 && (
        <select 
          className="absolute top-2 right-2 z-20 text-[10px] px-2 py-1 bg-black/50 border border-white/20 text-white rounded"
          value={selectedDeviceId}
          onChange={(e) => setSelectedDeviceId(e.target.value)}
        >
          {devices.map(d => (
            <option key={d.deviceId} value={d.deviceId}>
              {d.label || `Camera ${d.deviceId.slice(0, 5)}...`}
            </option>
          ))}
        </select>
      )}

      {/* Video Container — fills full height */}
      <div className="relative overflow-hidden border border-[#e2e8f0] bg-black h-full">
        <video
          ref={videoRef}
          className="w-full h-full object-cover -scale-x-100"
          playsInline
          muted
        />

        <PoseOverlay
          landmarks={currentLandmarks}
          width={width}
          height={height}
        />

        {/* Loading Overlay */}
        {(!cameraReady || isLoading) && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/70 gap-3">
            <div className="w-8 h-8 border-2 border-[var(--pke-accent)] border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-white/60">
              {!cameraReady
                ? "Starting camera…"
                : "Loading MediaPipe model…"}
            </p>
          </div>
        )}
      </div>

      {/* Error */}
      {(cameraError || mpError) && (
        <div className="absolute bottom-2 left-2 right-2 z-20 p-2 bg-[rgba(239,68,68,0.9)] text-[10px] text-white">
          {cameraError || mpError}
        </div>
      )}
    </div>
  );
}

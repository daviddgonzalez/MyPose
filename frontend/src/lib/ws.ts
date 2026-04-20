/**
 * WebSocket client for the PKE live streaming endpoint.
 * Matches the backend protocol at /ws/v1/stream.
 */

import type { WSFrameMessage, WSIncomingMessage } from "./types";

const WS_BASE_URL =
  process.env.NEXT_PUBLIC_WS_URL ||
  (typeof window !== "undefined"
    ? `ws://${window.location.hostname}:8000`
    : "ws://localhost:8000");

export type WSEventHandler = (message: WSIncomingMessage) => void;
export type WSErrorHandler = (error: Event | Error) => void;

interface PKEWebSocketOptions {
  /** Called on every incoming message (ack, result, session_end). */
  onMessage?: WSEventHandler;
  /** Called on connection errors. */
  onError?: WSErrorHandler;
  /** Called when connection is established. */
  onOpen?: () => void;
  /** Called when connection is closed. */
  onClose?: () => void;
  /** Max reconnection attempts (default 5). */
  maxReconnectAttempts?: number;
}

export class PKEWebSocket {
  private ws: WebSocket | null = null;
  private frameIdx = 0;
  private reconnectAttempts = 0;
  private maxReconnectAttempts: number;
  private options: PKEWebSocketOptions;
  private _isConnected = false;

  constructor(options: PKEWebSocketOptions = {}) {
    this.options = options;
    this.maxReconnectAttempts = options.maxReconnectAttempts ?? 5;
  }

  get isConnected(): boolean {
    return this._isConnected;
  }

  /**
   * Connect to the WebSocket streaming endpoint.
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    const url = `${WS_BASE_URL}/ws/v1/stream`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this._isConnected = true;
      this.reconnectAttempts = 0;
      this.frameIdx = 0;
      this.options.onOpen?.();
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as WSIncomingMessage;
        this.options.onMessage?.(data);
      } catch {
        console.error("Failed to parse WS message:", event.data);
      }
    };

    this.ws.onerror = (event: Event) => {
      console.error("WebSocket error:", event);
      this.options.onError?.(event);
    };

    this.ws.onclose = () => {
      this._isConnected = false;
      this.options.onClose?.();
    };
  }

  /**
   * Send a single frame of landmarks to the server.
   * landmarks should be a 33-element array of [x, y, z] arrays.
   */
  sendFrame(landmarks: number[][]): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn("WebSocket not connected, cannot send frame");
      return;
    }

    const message: WSFrameMessage = {
      type: "frame",
      frame_idx: this.frameIdx++,
      landmarks,
    };

    this.ws.send(JSON.stringify(message));
  }

  /**
   * Signal the server that the session has ended.
   */
  endSession(): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify({ type: "end" }));
  }

  /**
   * Send the configuration payload to the server.
   */
  sendConfig(strictness: string, exercise: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify({ type: "config", strictness, exercise }));
  }

  /**
   * Disconnect and cleanup.
   */
  disconnect(): void {
    if (this.ws) {
      this.ws.onclose = null; // Prevent reconnect on intentional close
      this.ws.close();
      this.ws = null;
    }
    this._isConnected = false;
    this.frameIdx = 0;
  }

  /**
   * Attempt reconnection with exponential backoff.
   */
  reconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error("Max reconnection attempts reached");
      this.options.onError?.(new Error("Max reconnection attempts reached"));
      return;
    }

    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000);
    this.reconnectAttempts++;

    console.log(
      `Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`
    );

    setTimeout(() => this.connect(), delay);
  }
}

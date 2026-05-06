"use client";

export interface AppUser {
  userId: string;
  username: string;
}

const STORAGE_KEY = "mypose_active_user";
const USER_EVENT = "mypose:user-updated";

export function getStoredUser(): AppUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as Partial<AppUser>;
    if (!parsed.userId || !parsed.username) return null;
    return { userId: parsed.userId, username: parsed.username };
  } catch {
    return null;
  }
}

export function saveStoredUser(user: AppUser): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event(USER_EVENT));
}

export function clearStoredUser(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new Event(USER_EVENT));
}

export function getUserUpdatedEventName(): string {
  return USER_EVENT;
}

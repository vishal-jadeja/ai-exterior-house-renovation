"use client";
import { create } from "zustand";

export type User = { id: string; email: string };

type AuthState = {
  token: string | null;
  user: User | null;
  hydrated: boolean;
  setToken: (t: string | null) => void;
  setUser: (u: User | null) => void;
  setHydrated: () => void;
  clear: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  hydrated: false,
  setToken: (token) => set({ token }),
  setUser: (user) => set({ user }),
  setHydrated: () => set({ hydrated: true }),
  clear: () => set({ token: null, user: null }),
}));

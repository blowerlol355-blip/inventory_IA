"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, type ReactNode } from "react";

import { api, publicPost, tokens } from "@/lib/api";
import type { TokenPair, User } from "@/lib/types";

interface AuthContextValue {
  user: User | undefined;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (organizationName: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const router = useRouter();

  const { data: user, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/api/v1/auth/me"),
    enabled: typeof window !== "undefined" && Boolean(tokens.access),
    retry: false,
    staleTime: 5 * 60_000,
  });

  const logout = useCallback(() => {
    tokens.clear();
    queryClient.clear();
    router.replace("/login");
  }, [queryClient, router]);

  useEffect(() => {
    // authFetch emite este evento cuando la sesión ya no se puede renovar.
    window.addEventListener("findocs:logout", logout);
    return () => window.removeEventListener("findocs:logout", logout);
  }, [logout]);

  const start = useCallback(
    async (pair: TokenPair) => {
      tokens.save(pair);
      await queryClient.fetchQuery({ queryKey: ["me"], queryFn: () => api<User>("/api/v1/auth/me") });
    },
    [queryClient],
  );

  const value: AuthContextValue = {
    user,
    isLoading,
    logout,
    login: async (email, password) =>
      start(await publicPost<TokenPair>("/api/v1/auth/login", { email, password })),
    register: async (organizationName, email, password) =>
      start(
        await publicPost<TokenPair>("/api/v1/auth/register", {
          organization_name: organizationName,
          email,
          password,
        }),
      ),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de AuthProvider");
  return ctx;
}

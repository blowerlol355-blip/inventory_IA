"use client";

import { useQuery } from "@tanstack/react-query";
import { FileSearch, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { ApiError, publicGet } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface AuthOptions {
  registration: boolean;
  demo: boolean;
}

// En el plan gratuito el servidor se duerme: si tarda más que esto, se avisa al visitante.
const SLOW_WAKE_MS = 3000;

function useAuthOptions() {
  const [slow, setSlow] = useState(false);
  const query = useQuery({
    queryKey: ["auth-options"],
    queryFn: () => publicGet<AuthOptions>("/api/v1/auth/options"),
    retry: 6,
    retryDelay: 5000,
    staleTime: Infinity,
  });
  useEffect(() => {
    if (!query.isPending) return;
    const timer = setTimeout(() => setSlow(true), SLOW_WAKE_MS);
    return () => clearTimeout(timer);
  }, [query.isPending]);
  return { options: query.data, waking: query.isPending && slow };
}

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { login, register, demo } = useAuth();
  const router = useRouter();
  const { options, waking } = useAuthOptions();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const isRegister = mode === "register";
  const registrationClosed = options?.registration === false;

  async function run(action: () => Promise<void>) {
    setPending(true);
    setError(null);
    try {
      await action();
      router.replace("/documents");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo conectar con el servidor");
    } finally {
      setPending(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email"));
    const password = String(form.get("password"));
    void run(() =>
      isRegister ? register(String(form.get("organization")), email, password) : login(email, password),
    );
  }

  return (
    <main className="flex flex-1 items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="mb-2 flex items-center gap-2 font-semibold">
            <FileSearch className="size-5" /> FinDocs AI
          </div>
          <CardTitle>{isRegister ? "Crea tu organización" : "Inicia sesión"}</CardTitle>
          <CardDescription>
            {isRegister
              ? "Serás el administrador de la nueva organización."
              : "Consulta documentos financieros en lenguaje natural, con respuestas citadas."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {waking && (
            <p role="status" className="rounded-md bg-muted p-3 text-sm text-muted-foreground">
              Despertando el servidor (plan gratuito): puede tardar hasta un minuto…
            </p>
          )}

          {!isRegister && options?.demo && (
            <>
              <Button size="lg" disabled={pending} onClick={() => void run(demo)}>
                <Sparkles /> {pending ? "Preparando la demo…" : "Probar demo"}
              </Button>
              <p className="text-center text-xs text-muted-foreground">
                Sin registro: 50 documentos de ejemplo (facturas, contratos, Excel, Word…). Pregunta,
                convierte o comprime archivos desde el chat.
              </p>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <Separator className="flex-1" /> o con tu cuenta <Separator className="flex-1" />
              </div>
            </>
          )}

          {isRegister && registrationClosed ? (
            <p className="text-sm text-muted-foreground">
              El registro está cerrado en esta demo.{" "}
              <Link className="underline" href="/login">
                Prueba la demo
              </Link>
              .
            </p>
          ) : (
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              {isRegister && (
                <div className="grid gap-2">
                  <Label htmlFor="organization">Organización</Label>
                  <Input id="organization" name="organization" required minLength={2} />
                </div>
              )}
              <div className="grid gap-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" name="email" type="email" autoComplete="email" required />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="password">Contraseña</Label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  minLength={isRegister ? 8 : undefined}
                  required
                />
              </div>
              <Button type="submit" variant={options?.demo && !isRegister ? "outline" : "default"} disabled={pending}>
                {pending ? "Un momento…" : isRegister ? "Crear cuenta" : "Entrar"}
              </Button>
            </form>
          )}

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

          {!registrationClosed && (
            <p className="text-center text-sm text-muted-foreground">
              {isRegister ? "¿Ya tienes cuenta? " : "¿No tienes cuenta? "}
              <Link className="underline" href={isRegister ? "/login" : "/register"}>
                {isRegister ? "Inicia sesión" : "Regístrate"}
              </Link>
            </p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}

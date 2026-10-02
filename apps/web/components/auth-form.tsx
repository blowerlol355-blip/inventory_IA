"use client";

import { FileSearch } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const isRegister = mode === "register";

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email"));
    const password = String(form.get("password"));
    setPending(true);
    setError(null);
    try {
      if (isRegister) await register(String(form.get("organization")), email, password);
      else await login(email, password);
      router.replace("/documents");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo conectar con el servidor");
    } finally {
      setPending(false);
    }
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
              : "Consulta tus documentos financieros con respuestas citadas."}
          </CardDescription>
        </CardHeader>
        <CardContent>
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
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <Button type="submit" disabled={pending}>
              {pending ? "Un momento…" : isRegister ? "Crear cuenta" : "Entrar"}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              {isRegister ? "¿Ya tienes cuenta? " : "¿No tienes cuenta? "}
              <Link className="underline" href={isRegister ? "/login" : "/register"}>
                {isRegister ? "Inicia sesión" : "Regístrate"}
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

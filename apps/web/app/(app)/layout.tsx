"use client";

import { FileSearch, FileText, FolderDown, LogOut, MessageSquare } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { tokens } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/documents", label: "Documentos", icon: FileText },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/files", label: "Archivos", icon: FolderDown },
];

export default function AppLayout({ children }: { children: ReactNode }) {
  const { user, isLoading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!tokens.access) router.replace("/login");
  }, [router]);

  if (isLoading || !user) {
    return <div className="flex flex-1 items-center justify-center text-muted-foreground">Cargando…</div>;
  }

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex h-14 shrink-0 items-center gap-4 border-b px-4">
        <Link href="/documents" className="flex items-center gap-2 font-semibold">
          <FileSearch className="size-5" /> FinDocs AI
        </Link>
        <nav className="flex gap-1">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                buttonVariants({ variant: pathname.startsWith(href) ? "secondary" : "ghost" }),
              )}
            >
              <Icon /> {label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm">
          <span className="hidden text-muted-foreground sm:inline">
            {user.organization_name} · {user.email} ({user.role})
          </span>
          <Button variant="ghost" size="sm" onClick={logout}>
            <LogOut /> Salir
          </Button>
        </div>
      </header>
      <main className="min-h-0 flex-1">{children}</main>
    </div>
  );
}

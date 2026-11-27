"use client";

import {
  CalendarDays,
  ChevronsUpDown,
  LayoutDashboard,
  LogOut,
  Menu,
  PanelLeft,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useAuth } from "@/components/providers/auth-provider";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  EventSelectionProvider,
  useEventSelection,
} from "@/components/layout/event-selection-context";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

export type ShellUser = {
  id: string;
  email?: string | null;
  name?: string | null;
};

type NavItem = {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  requiresEventManagement?: boolean;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  {
    href: "/events",
    label: "Events",
    icon: CalendarDays,
    requiresEventManagement: true,
  },
];

export function AppShell({
  user,
  canManageEvents,
  children,
}: {
  user: ShellUser;
  canManageEvents: boolean;
  children: ReactNode;
}) {
  return (
    <EventSelectionProvider>
      <ShellContent user={user} canManageEvents={canManageEvents}>
        {children}
      </ShellContent>
    </EventSelectionProvider>
  );
}

function ShellContent({
  user,
  canManageEvents,
  children,
}: {
  user: ShellUser;
  canManageEvents: boolean;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const { signOut } = useAuth();
  const { selectedEventSlug } = useEventSelection();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const visibleNav = NAV_ITEMS.filter(
    (item) => !item.requiresEventManagement || canManageEvents,
  );
  const authUser = useAuth().user;
  const displayName = authUser?.user_metadata?.full_name ?? user.name ?? "Workspace user";
  const email = authUser?.email ?? user.email ?? "";

  const navLinks = (onNavigate?: () => void) =>
    visibleNav.map((item) => {
      const Icon = item.icon;
      const active = pathname === item.href;

      return (
        <Link
          key={item.href}
          href={item.href}
          onClick={onNavigate}
          className={cn(
            "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
            active
              ? "bg-primary/10 text-primary"
              : "text-muted-foreground hover:bg-accent hover:text-foreground",
          )}
          aria-current={active ? "page" : undefined}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
          {item.label}
        </Link>
      );
    });

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[16rem_1fr]">
      <aside className="sticky top-0 hidden h-screen flex-col border-r border-border bg-card px-4 py-6 lg:flex">
        <div className="flex items-center gap-3 px-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <CalendarDays className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <p className="text-sm font-semibold leading-tight">Event Operations</p>
            <p className="text-xs text-muted-foreground">Admin workspace</p>
          </div>
        </div>

        <nav className="mt-8 flex-1 space-y-1" aria-label="Main navigation">
          {navLinks()}
        </nav>

        <div className="rounded-lg border border-border bg-muted/50 p-3 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">Access model</p>
          <p className="mt-1 leading-5">
            The backend validates every request against your event staff role.
          </p>
        </div>
      </aside>

      <div className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-30 border-b border-border bg-card/90 backdrop-blur">
          <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
            <Dialog open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
              <DialogTrigger asChild>
                <button
                  type="button"
                  className="inline-flex h-10 w-10 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
                  aria-label="Open navigation menu"
                >
                  <Menu className="h-5 w-5" aria-hidden="true" />
                </button>
              </DialogTrigger>
              <DialogContent
                showClose={false}
                className="left-0 top-0 h-dvh max-w-[18rem] translate-x-0 translate-y-0 rounded-none border-y-0 border-l-0 p-4 lg:hidden"
              >
                <DialogTitle className="sr-only">Navigation</DialogTitle>
                <DialogDescription className="sr-only">
                  Choose a page in the event workspace.
                </DialogDescription>
                <div className="mb-6 flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                    <CalendarDays className="h-5 w-5" aria-hidden="true" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold">Event Operations</p>
                    <p className="text-xs text-muted-foreground">Admin workspace</p>
                  </div>
                </div>
                <nav className="space-y-1" aria-label="Mobile navigation">
                  {navLinks(() => setMobileNavOpen(false))}
                </nav>
                <DialogClose asChild>
                  <button type="button" className="sr-only">
                    Close navigation
                  </button>
                </DialogClose>
              </DialogContent>
            </Dialog>

            <div className="hidden items-center gap-2 text-sm text-muted-foreground sm:flex">
              <PanelLeft className="h-4 w-4" aria-hidden="true" />
              <span>Workspace</span>
            </div>

            <div className="ml-auto flex items-center gap-3">
              <div className="hidden max-w-52 truncate rounded-full border border-border bg-muted/50 px-3 py-1 text-xs text-muted-foreground sm:block">
                {selectedEventSlug ? (
                  <span title={selectedEventSlug}>Event: {selectedEventSlug}</span>
                ) : (
                  <span>No event selected</span>
                )}
              </div>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className="flex items-center gap-2 rounded-lg p-1 pr-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    aria-label="Open profile menu"
                  >
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                      {initials(displayName, email)}
                    </span>
                    <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-64">
                  <DropdownMenuLabel>
                    <span className="block truncate text-sm font-medium text-foreground">
                      {displayName}
                    </span>
                    <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                      {email || "Authenticated user"}
                    </span>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={() => void signOut()} className="text-destructive">
                    <LogOut className="h-4 w-4" aria-hidden="true" />
                    Sign out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mx-auto w-full max-w-7xl">{children}</div>
        </main>
      </div>
    </div>
  );
}

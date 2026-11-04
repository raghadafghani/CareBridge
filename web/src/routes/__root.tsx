import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
  type ErrorComponentProps,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl text-foreground">404</h1>
        <p className="mt-2 text-sm text-muted-foreground">This page doesn't exist.</p>
        <Link
          to="/"
          className="mt-6 inline-flex rounded-full bg-primary px-5 py-2 text-sm text-primary-foreground"
        >
          Go home
        </Link>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: ErrorComponentProps) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-3xl text-foreground">This page didn't load</h1>
        <button
          onClick={() => {
            router.invalidate();
            reset();
          }}
          className="mt-6 rounded-full bg-primary px-5 py-2 text-sm text-primary-foreground"
        >
          Try again
        </button>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "CareBridge — Post-Discharge Care Assistant" },
      {
        name: "description",
        content: "CareBridge turns hospital discharge reports into clear, personalized care plans.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "icon", href: "/favicon.ico", type: "image/x-icon" },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Manrope:wght@400;500;600;700&display=swap",
      },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-3.5" aria-label="CareBridge, home">
      <svg viewBox="0 0 80 64" className="h-14 w-[4.4rem] shrink-0" aria-hidden="true">
        <path
          fill="var(--primary)"
          d="M40 62C16 48 3 37 3 25 3 13 13 5 23 5c6.2 0 10.4 3.2 13 7.2C38.6 8.2 42.8 5 49 5c10 0 20 8 20 20C69 37 56 48 40 62z"
        />
        <path
          d="M18 16v30M54 16v30"
          fill="none"
          stroke="var(--primary-foreground)"
          strokeWidth="3.6"
          strokeLinecap="square"
        />
        <path
          d="M12 16h12M48 16h12"
          fill="none"
          stroke="var(--primary-foreground)"
          strokeWidth="3.2"
          strokeLinecap="square"
        />
        <path
          d="M4 40h64"
          fill="none"
          stroke="var(--primary-foreground)"
          strokeWidth="4.2"
          strokeLinecap="square"
        />
        <path
          d="M6 40L18 16Q36 46 54 16L66 40"
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2.3"
          strokeLinejoin="round"
        />
        <path
          d="M24 28v12M30 33v7M42 33v7M48 28v12"
          fill="none"
          stroke="var(--primary-foreground)"
          strokeWidth="1.6"
        />
      </svg>
      <span className="font-display text-[1.7rem] leading-none tracking-tight">CareBridge</span>
    </Link>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  const nav = "text-sm text-muted-foreground hover:text-foreground transition-colors";
  return (
    <QueryClientProvider client={queryClient}>
      <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-20 max-w-6xl items-center justify-between px-6">
          <Logo />
          <nav className="flex items-center gap-6">
            <Link
              to="/"
              className={nav}
              activeOptions={{ exact: true }}
              activeProps={{ className: "text-foreground" }}
            >
              Overview
            </Link>
            <Link to="/plan" className={nav} activeProps={{ className: "text-foreground" }}>
              Care plan
            </Link>
            <Link to="/check-in" className={nav} activeProps={{ className: "text-foreground" }}>
              Check-in
            </Link>
            <Link
              to="/upload"
              className="rounded-full bg-ink px-4 py-2 text-sm text-ink-foreground hover:opacity-90"
            >
              Upload report
            </Link>
          </nav>
        </div>
      </header>
      <Outlet />
      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-6 py-8 text-xs text-muted-foreground sm:flex-row sm:justify-between">
          <span>
            CareBridge · Built with AWS Strands Agents SDK · Strands SDK Workshop to Ship Hackathon
          </span>
          <span>Not a substitute for professional medical advice.</span>
        </div>
      </footer>
    </QueryClientProvider>
  );
}

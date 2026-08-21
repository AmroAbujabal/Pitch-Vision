import Link from "next/link";
import { cookies } from "next/headers";
import SignOutButton from "./SignOutButton";
import { SESSION_COOKIE } from "@/lib/session";

// SVG pitch icon — no emoji
function PitchIcon() {
  return (
    <svg
      aria-hidden="true"
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect
        x="1"
        y="3"
        width="18"
        height="14"
        rx="1.5"
        stroke="white"
        strokeWidth="1.5"
      />
      <line x1="10" y1="3" x2="10" y2="17" stroke="white" strokeWidth="1.5" />
      <circle cx="10" cy="10" r="2.5" stroke="white" strokeWidth="1.5" />
      <path
        d="M1 6.5h2.5M1 13.5h2.5M16.5 6.5H19M16.5 13.5H19"
        stroke="white"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function Nav() {
  // Signed out, the only page reachable is /login, where "Sign out" and a link
  // to the match list are both dead ends.
  const signedIn = cookies().has(SESSION_COOKIE);

  return (
    <>
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>
      <nav
        className="sticky top-0 z-40 border-b border-slate-800"
        style={{ background: "#0F172A", height: "var(--header-height)" }}
      >
        <div className="mx-auto flex h-full max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          {/* Brand */}
          <Link
            href="/"
            className="flex items-center gap-2.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 rounded"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-800">
              <PitchIcon />
            </span>
            <span
              className="text-[15px] font-semibold tracking-tight text-white"
              style={{ fontFamily: "'Fira Code', monospace" }}
            >
              pitch<span className="text-blue-400">vision</span>
            </span>
          </Link>

          {/* Right side */}
          <div className="flex items-center gap-6">
            {signedIn && (
              <>
                <Link
                  href="/"
                  className="text-xs font-medium text-slate-400 hover:text-white transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 rounded px-1"
                >
                  Matches
                </Link>
                <SignOutButton />
              </>
            )}
          </div>
        </div>
      </nav>
    </>
  );
}

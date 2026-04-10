"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "排行榜" },
  { href: "/rounds", label: "评测轮次" },
  { href: "/problems", label: "题库" },
  { href: "/new-round", label: "发起新评测" },
  { href: "/models", label: "模型管理" },
];

export default function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <nav className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        <Link href="/"
          className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent shrink-0">
          AICoderBench
        </Link>

        {/* Desktop links */}
        <div className="hidden sm:flex gap-6">
          {links.map((l) => (
            <Link key={l.href} href={l.href}
              className={`text-sm transition-colors ${
                isActive(l.href) ? "text-cyan-400" : "text-gray-400 hover:text-white"
              }`}>
              {l.label}
            </Link>
          ))}
        </div>

        {/* Mobile hamburger */}
        <button
          onClick={() => setOpen((o) => !o)}
          className="sm:hidden p-1 text-gray-400 hover:text-white"
          aria-label="菜单"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {open ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
      </div>

      {/* Mobile menu */}
      {open && (
        <div className="sm:hidden border-t border-gray-800 bg-gray-950 px-4 py-3 space-y-1">
          {links.map((l) => (
            <Link key={l.href} href={l.href}
              onClick={() => setOpen(false)}
              className={`block py-2 text-sm transition-colors ${
                isActive(l.href) ? "text-cyan-400" : "text-gray-400"
              }`}>
              {l.label}
            </Link>
          ))}
        </div>
      )}
    </nav>
  );
}

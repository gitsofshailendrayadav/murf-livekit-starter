'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BarChart3, Bot, Radio } from 'lucide-react';
import type { AppConfig } from '@/app-config';
import { cn } from '@/lib/shadcn/utils';

interface NavBarProps {
  appConfig: AppConfig;
}

export function NavBar({ appConfig }: NavBarProps) {
  const pathname = usePathname();
  const { companyName, logo, logoDark } = appConfig;

  const isVoiceActive = pathname === '/';
  const isAnalyticsActive = pathname.startsWith('/analytics');

  return (
    <header className="border-border/40 bg-background/80 fixed top-0 left-0 z-50 w-full border-b backdrop-blur-md transition-all">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Brand / Logo */}
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="group flex items-center gap-2.5 transition-transform hover:scale-105"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={logo} alt={`${companyName} Logo`} className="block size-7 dark:hidden" />
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={logoDark ?? logo}
              alt={`${companyName} Logo`}
              className="hidden size-7 dark:block"
            />
            <div className="flex flex-col">
              <span className="text-foreground font-sans text-base font-bold tracking-tight">
                {companyName}
              </span>
              <span className="text-muted-foreground hidden font-mono text-[10px] tracking-wider uppercase sm:inline-block">
                AI Financial Assistant
              </span>
            </div>
          </Link>
        </div>

        {/* Central Navigation Tabs */}
        <nav className="border-border/60 bg-muted/40 flex items-center gap-1.5 rounded-full border p-1 shadow-inner backdrop-blur-sm">
          <Link
            href="/"
            className={cn(
              'flex items-center gap-2 rounded-full px-4 py-1.5 font-sans text-xs font-semibold tracking-wide transition-all duration-200',
              isVoiceActive
                ? 'bg-primary text-primary-foreground shadow-sm'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground'
            )}
          >
            <Bot className="size-3.5" />
            <span>Voice Agent</span>
          </Link>

          <Link
            href="/analytics"
            className={cn(
              'flex items-center gap-2 rounded-full px-4 py-1.5 font-sans text-xs font-semibold tracking-wide transition-all duration-200',
              isAnalyticsActive
                ? 'bg-primary text-primary-foreground shadow-sm'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground'
            )}
          >
            <BarChart3 className="size-3.5" />
            <span>Call Analytics</span>
          </Link>
        </nav>

        {/* Live Status Badge */}
        <div className="hidden items-center gap-2 md:flex">
          <div className="flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
            <Radio className="size-3 animate-pulse text-emerald-500" />
            <span>LiveKit &bull; Day 8</span>
          </div>
        </div>
      </div>
    </header>
  );
}

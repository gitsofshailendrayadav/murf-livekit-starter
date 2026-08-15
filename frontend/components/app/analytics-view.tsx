'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  Globe,
  Phone,
  PhoneCall,
  Radio,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  XCircle,
} from 'lucide-react';
import type { AnalyticsSummary } from '@/app/api/analytics/route';
import { Button } from '@/components/ui/button';

export function AnalyticsView() {
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchAnalytics = useCallback(async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true);
    try {
      const res = await fetch('/api/analytics', { cache: 'no-store' });
      if (res.ok) {
        const json: AnalyticsSummary = await res.json();
        setData(json);
        setLastUpdated(new Date());
      }
    } catch (err) {
      console.error('Failed to fetch analytics:', err);
    } finally {
      setLoading(false);
      if (isManualRefresh) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchAnalytics();
    const interval = setInterval(() => {
      fetchAnalytics();
    }, 4000);
    return () => clearInterval(interval);
  }, [fetchAnalytics]);

  const formatDuration = (seconds: number) => {
    const s = Math.max(0, Math.round(seconds || 0));
    const mins = Math.floor(s / 60);
    const remainder = s % 60;
    return `${mins.toString().padStart(2, '0')}:${remainder.toString().padStart(2, '0')}`;
  };

  const totalCalls = data?.total_calls ?? 0;
  const successfulCalls = data?.successful_calls ?? 0;
  const failedCalls = data?.failed_calls ?? 0;
  const successRate = data?.success_rate_percent ?? 0;
  const avgDuration = data?.avg_duration_seconds ?? 0;
  const browserCalls = data?.browser_calls ?? 0;
  const sipCalls = data?.sip_calls ?? 0;
  const recentCalls = data?.recent_calls ?? [];

  return (
    <div className="bg-background text-foreground min-h-screen pt-24 pb-16">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Top Header & Back Navigation */}
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="outline"
              size="sm"
              asChild
              className="border-border/80 bg-background hover:bg-muted gap-2 rounded-full font-mono text-xs font-semibold"
            >
              <Link href="/">
                <ArrowLeft className="size-4" />
                Back to Voice Agent
              </Link>
            </Button>
            <div>
              <h1 className="text-foreground text-2xl font-bold tracking-tight sm:text-3xl">
                Call Intelligence & Analytics
              </h1>
              <p className="text-muted-foreground mt-0.5 text-xs sm:text-sm">
                Real-time persistent session logs & metrics from FinSaathi Voice Agent
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {lastUpdated && (
              <span className="text-muted-foreground font-mono text-[11px]">
                Updated {lastUpdated.toLocaleTimeString()}
              </span>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => fetchAnalytics(true)}
              disabled={refreshing}
              className="gap-1.5 rounded-full font-mono text-xs"
            >
              <RefreshCw className={`size-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        </div>

        {/* Primary Metric KPI Cards */}
        <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* Total Calls */}
          <div className="border-border/70 bg-card hover:border-primary/40 rounded-2xl border p-5 shadow-sm transition-all">
            <div className="text-muted-foreground mb-3 flex items-center justify-between">
              <span className="font-mono text-xs font-semibold tracking-wider uppercase">
                Total Calls
              </span>
              <div className="bg-primary/10 text-primary flex size-9 items-center justify-center rounded-xl">
                <PhoneCall className="size-4" />
              </div>
            </div>
            <div className="text-foreground text-3xl font-extrabold tracking-tight">
              {loading ? '—' : totalCalls}
            </div>
            <div className="text-muted-foreground mt-2 flex items-center gap-1.5 text-xs">
              <Radio className="size-3 animate-pulse text-emerald-500" />
              <span>Persistent SQLite Records</span>
            </div>
          </div>

          {/* Successful Calls */}
          <div className="bg-card rounded-2xl border border-emerald-500/20 p-5 shadow-sm transition-all hover:border-emerald-500/40">
            <div className="text-muted-foreground mb-3 flex items-center justify-between">
              <span className="font-mono text-xs font-semibold tracking-wider text-emerald-600 uppercase dark:text-emerald-400">
                Successful Calls
              </span>
              <div className="flex size-9 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="size-4" />
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <div className="text-3xl font-extrabold tracking-tight text-emerald-600 dark:text-emerald-400">
                {loading ? '—' : successfulCalls}
              </div>
              <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                {successRate}% rate
              </span>
            </div>
            <div className="text-muted-foreground mt-2 flex items-center gap-1 text-xs">
              <TrendingUp className="size-3 text-emerald-500" />
              <span>Resolved interactions</span>
            </div>
          </div>

          {/* Failed Calls */}
          <div className="border-destructive/20 bg-card hover:border-destructive/40 rounded-2xl border p-5 shadow-sm transition-all">
            <div className="text-muted-foreground mb-3 flex items-center justify-between">
              <span className="text-destructive font-mono text-xs font-semibold tracking-wider uppercase">
                Failed Calls
              </span>
              <div className="bg-destructive/10 text-destructive flex size-9 items-center justify-center rounded-xl">
                <XCircle className="size-4" />
              </div>
            </div>
            <div className="text-destructive text-3xl font-extrabold tracking-tight">
              {loading ? '—' : failedCalls}
            </div>
            <div className="text-muted-foreground mt-2 flex items-center gap-1 text-xs">
              <span>Disconnected prior to resolution</span>
            </div>
          </div>

          {/* Average Duration */}
          <div className="border-border/70 bg-card hover:border-primary/40 rounded-2xl border p-5 shadow-sm transition-all">
            <div className="text-muted-foreground mb-3 flex items-center justify-between">
              <span className="font-mono text-xs font-semibold tracking-wider uppercase">
                Avg Duration
              </span>
              <div className="bg-primary/10 text-primary flex size-9 items-center justify-center rounded-xl">
                <Clock className="size-4" />
              </div>
            </div>
            <div className="text-foreground font-mono text-3xl font-extrabold tracking-tight">
              {loading ? '—' : formatDuration(avgDuration)}
            </div>
            <div className="text-muted-foreground mt-2 flex items-center gap-2 text-xs">
              <span className="flex items-center gap-1">
                <Globe className="size-3" /> {browserCalls} Web
              </span>
              <span>&bull;</span>
              <span className="flex items-center gap-1">
                <Phone className="size-3" /> {sipCalls} SIP
              </span>
            </div>
          </div>
        </div>

        {/* Real-time Call Log Table */}
        <div className="border-border/80 bg-card overflow-hidden rounded-2xl border shadow-sm">
          <div className="border-border/70 bg-muted/20 flex items-center justify-between border-b px-6 py-4">
            <div className="flex items-center gap-2.5">
              <ShieldCheck className="text-primary size-4" />
              <h2 className="text-foreground text-base font-semibold">
                Recent Call Session Records
              </h2>
            </div>
            <span className="text-muted-foreground font-mono text-xs">
              {recentCalls.length} records found
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-border/60 bg-muted/40 text-muted-foreground border-b font-mono text-[11px] font-semibold tracking-wider uppercase">
                <tr>
                  <th className="px-6 py-3.5">Call ID</th>
                  <th className="px-6 py-3.5">Started At</th>
                  <th className="px-6 py-3.5">Channel</th>
                  <th className="px-6 py-3.5">Duration</th>
                  <th className="px-6 py-3.5">Outcome</th>
                  <th className="px-6 py-3.5">Resolution / Reason</th>
                </tr>
              </thead>
              <tbody className="divide-border/40 divide-y">
                {loading ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="text-muted-foreground px-6 py-12 text-center font-mono text-xs"
                    >
                      Loading call intelligence records...
                    </td>
                  </tr>
                ) : recentCalls.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-14 text-center">
                      <div className="text-muted-foreground flex flex-col items-center justify-center gap-2">
                        <PhoneCall className="text-muted-foreground/50 size-8 stroke-1" />
                        <p className="text-sm font-medium">No call records found yet</p>
                        <p className="max-w-sm text-xs">
                          Start a voice session from the Voice Agent tab to record live telemetry
                          and analytics.
                        </p>
                        <Button asChild size="sm" className="mt-3 rounded-full font-mono text-xs">
                          <Link href="/">Launch Voice Agent</Link>
                        </Button>
                      </div>
                    </td>
                  </tr>
                ) : (
                  recentCalls.map((call) => {
                    const isSuccess = (call.outcome || '').toLowerCase() === 'success';
                    const isSip = (call.channel || '').toLowerCase().includes('sip');
                    const reason = (isSuccess ? call.success_reason : call.failure_reason) || '—';

                    return (
                      <tr key={call.call_id} className="hover:bg-muted/30 transition-colors">
                        {/* Call ID */}
                        <td className="text-foreground px-6 py-4 font-mono text-xs font-bold whitespace-nowrap">
                          {call.call_id}
                        </td>

                        {/* Started At */}
                        <td className="text-muted-foreground px-6 py-4 font-mono text-xs whitespace-nowrap">
                          {call.started_at}
                        </td>

                        {/* Channel Badge */}
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-mono text-[10px] font-semibold uppercase ${
                              isSip
                                ? 'border border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400'
                                : 'border-primary/30 bg-primary/10 text-primary border'
                            }`}
                          >
                            {isSip ? (
                              <Phone className="size-2.5" />
                            ) : (
                              <Globe className="size-2.5" />
                            )}
                            {call.channel}
                          </span>
                        </td>

                        {/* Duration */}
                        <td className="text-foreground px-6 py-4 font-mono text-xs whitespace-nowrap">
                          {formatDuration(call.duration_seconds)}
                        </td>

                        {/* Outcome Badge */}
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase ${
                              isSuccess
                                ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                                : 'border-destructive/30 bg-destructive/10 text-destructive border'
                            }`}
                          >
                            {isSuccess ? (
                              <CheckCircle2 className="size-2.5" />
                            ) : (
                              <XCircle className="size-2.5" />
                            )}
                            {call.outcome}
                          </span>
                        </td>

                        {/* Reason / Details */}
                        <td
                          className="text-muted-foreground max-w-md truncate px-6 py-4 text-xs"
                          title={reason}
                        >
                          {reason}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

import { NextResponse } from 'next/server';
import fs from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';

export const dynamic = 'force-dynamic';

export interface CallRecord {
  call_id: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number;
  channel: string;
  outcome: string;
  success_reason: string | null;
  failure_reason: string | null;
  created_at: string;
}

export interface AnalyticsSummary {
  total_calls: number;
  successful_calls: number;
  failed_calls: number;
  in_progress_calls: number;
  avg_duration_seconds: number;
  browser_calls: number;
  sip_calls: number;
  success_rate_percent: number;
  recent_calls: CallRecord[];
}

function getDatabasePath(): string {
  // Support standard backend data path in local dev & deployment
  const primaryPath = path.resolve(process.cwd(), '../backend/data/call_analytics.db');
  if (fs.existsSync(primaryPath)) {
    return primaryPath;
  }
  const fallbackPath = path.resolve(process.cwd(), 'data/call_analytics.db');
  return fallbackPath;
}

function readAnalyticsFromDb(): AnalyticsSummary {
  const dbPath = getDatabasePath();

  if (!fs.existsSync(dbPath)) {
    return {
      total_calls: 0,
      successful_calls: 0,
      failed_calls: 0,
      in_progress_calls: 0,
      avg_duration_seconds: 0,
      browser_calls: 0,
      sip_calls: 0,
      success_rate_percent: 0,
      recent_calls: [],
    };
  }

  let db: DatabaseSync | null = null;
  try {
    db = new DatabaseSync(dbPath, { readOnly: true });

    // Ensure table exists
    const tableCheck = db
      .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='calls'")
      .get();

    if (!tableCheck) {
      return {
        total_calls: 0,
        successful_calls: 0,
        failed_calls: 0,
        in_progress_calls: 0,
        avg_duration_seconds: 0,
        browser_calls: 0,
        sip_calls: 0,
        success_rate_percent: 0,
        recent_calls: [],
      };
    }

    const rows = db
      .prepare('SELECT * FROM calls ORDER BY started_at DESC LIMIT 50')
      .all() as unknown as CallRecord[];

    const total_calls = rows.length;
    let successful_calls = 0;
    let failed_calls = 0;
    let in_progress_calls = 0;
    let browser_calls = 0;
    let sip_calls = 0;
    let total_duration = 0;
    let completed_duration_count = 0;

    for (const call of rows) {
      const outcome = (call.outcome || '').toLowerCase();
      if (outcome === 'success') {
        successful_calls++;
      } else if (outcome === 'failed') {
        failed_calls++;
      } else if (outcome === 'in_progress') {
        in_progress_calls++;
      }

      const channel = (call.channel || '').toLowerCase();
      if (channel.includes('sip')) {
        sip_calls++;
      } else {
        browser_calls++;
      }

      if (call.duration_seconds && call.duration_seconds > 0) {
        total_duration += call.duration_seconds;
        completed_duration_count++;
      }
    }

    const avg_duration_seconds =
      completed_duration_count > 0 ? Math.round(total_duration / completed_duration_count) : 0;
    const success_rate_percent =
      total_calls > 0 ? Number(((successful_calls / total_calls) * 100).toFixed(1)) : 0;

    return {
      total_calls,
      successful_calls,
      failed_calls,
      in_progress_calls,
      avg_duration_seconds,
      browser_calls,
      sip_calls,
      success_rate_percent,
      recent_calls: rows,
    };
  } catch (error) {
    console.error('Error reading call analytics DB:', error);
    return {
      total_calls: 0,
      successful_calls: 0,
      failed_calls: 0,
      in_progress_calls: 0,
      avg_duration_seconds: 0,
      browser_calls: 0,
      sip_calls: 0,
      success_rate_percent: 0,
      recent_calls: [],
    };
  } finally {
    if (db) {
      try {
        db.close();
      } catch {
        // ignore close errors
      }
    }
  }
}

export async function GET() {
  try {
    const data = readAnalyticsFromDb();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Analytics GET error:', error);
    return NextResponse.json(
      {
        total_calls: 0,
        successful_calls: 0,
        failed_calls: 0,
        in_progress_calls: 0,
        avg_duration_seconds: 0,
        browser_calls: 0,
        sip_calls: 0,
        success_rate_percent: 0,
        recent_calls: [],
      },
      { status: 200 }
    );
  }
}

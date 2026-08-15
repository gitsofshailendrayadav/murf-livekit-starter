from __future__ import annotations

import argparse
import html
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer

from analytics import (
    get_analytics_summary,
    get_recent_calls,
    init_analytics_db,
)
from escalation import get_all_escalations, init_escalations_db

logger = logging.getLogger("dashboard")


class UnifiedDashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        clean_path = self.path.split("?")[0].rstrip("/")
        if clean_path == "":
            clean_path = "/"

        if clean_path == "/api/analytics":
            self._handle_api_analytics()
        elif clean_path in ("/api/calls", "/calls/json"):
            self._handle_api_calls()
        elif clean_path in ("/api/escalations", "/escalations/json"):
            self._handle_api_escalations()
        elif clean_path == "/escalations":
            self._handle_html_escalations()
        elif clean_path in ("/", "/dashboard", "/analytics"):
            self._handle_html_analytics()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Page not found")

    def _send_json_response(self, data: dict) -> None:
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(payload)

    def _send_html_response(self, html_str: str) -> None:
        payload = html_str.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(payload)

    def _handle_api_analytics(self) -> None:
        summary = get_analytics_summary()
        self._send_json_response(
            {
                "total_calls": summary["total_calls"],
                "successful_calls": summary["successful_calls"],
                "failed_calls": summary["failed_calls"],
            }
        )

    def _handle_api_calls(self) -> None:
        summary = get_analytics_summary()
        recent = get_recent_calls(limit=50)
        self._send_json_response(
            {
                "total_calls": summary["total_calls"],
                "successful_calls": summary["successful_calls"],
                "failed_calls": summary["failed_calls"],
                "recent_calls": recent,
            }
        )

    def _handle_api_escalations(self) -> None:
        escalations = get_all_escalations()
        self._send_json_response(
            {"escalations": escalations, "count": len(escalations)}
        )

    def _handle_html_analytics(self) -> None:
        summary = get_analytics_summary()
        recent = get_recent_calls(limit=50)

        total_calls = summary["total_calls"]
        successful_calls = summary["successful_calls"]
        failed_calls = summary["failed_calls"]
        rate = (
            round((successful_calls / total_calls) * 100, 1) if total_calls > 0 else 0.0
        )

        rows_html = ""
        if not recent:
            rows_html = """
            <tr id="empty-row">
                <td colspan="6" class="empty-state">
                    No call records recorded yet. Start a real voice session to see live analytics.
                </td>
            </tr>
            """
        else:
            for call in recent:
                cid = html.escape(str(call.get("call_id", "")))
                started = html.escape(str(call.get("started_at", "")))
                dur = int(call.get("duration_seconds", 0) or 0)
                mins = dur // 60
                secs = dur % 60
                dur_formatted = f"{mins:02d}:{secs:02d}"

                channel = html.escape(str(call.get("channel", "browser")).upper())
                channel_cls = "badge-sip" if "SIP" in channel else "badge-browser"

                outcome = html.escape(str(call.get("outcome", "failed")).upper())
                outcome_cls = (
                    "badge-success" if outcome == "SUCCESS" else "badge-failed"
                )

                reason = (
                    call.get("success_reason")
                    if outcome == "SUCCESS"
                    else call.get("failure_reason")
                ) or "-"
                reason_clean = html.escape(str(reason))

                rows_html += f"""
                <tr>
                    <td class="font-mono"><strong>{cid}</strong></td>
                    <td class="time-cell">{started}</td>
                    <td><span class="badge {channel_cls}">{channel}</span></td>
                    <td class="font-mono">{dur_formatted}</td>
                    <td><span class="badge {outcome_cls}">{outcome}</span></td>
                    <td class="reason-cell">{reason_clean}</td>
                </tr>
                """

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FinSaathi Call Analytics &bull; Day 8</title>
    <style>
        :root {{
            --bg: #0b0f19;
            --card-bg: #151d30;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --border: #22314e;
            --accent: #38bdf8;
            --accent-glow: rgba(56, 189, 248, 0.15);
            --success: #10b981;
            --success-glow: rgba(16, 185, 129, 0.15);
            --failed: #ef4444;
            --failed-glow: rgba(239, 68, 68, 0.15);
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            padding: 2rem;
            line-height: 1.5;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.25rem;
        }}
        .brand-title {{
            font-size: 1.75rem;
            font-weight: 700;
            color: var(--accent);
            display: flex;
            align-items: center;
            gap: 0.6rem;
        }}
        .brand-sub {{
            color: var(--text-muted);
            font-size: 0.85rem;
            margin-top: 0.25rem;
        }}
        .nav-links {{
            display: flex;
            gap: 0.75rem;
            align-items: center;
        }}
        .nav-tab {{
            padding: 0.45rem 0.9rem;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 600;
            text-decoration: none;
            color: var(--text-muted);
            background: var(--card-bg);
            border: 1px solid var(--border);
            transition: all 0.2s ease;
        }}
        .nav-tab.active {{
            background: var(--accent);
            color: #0b0f19;
            border-color: var(--accent);
        }}
        .nav-tab:hover:not(.active) {{
            color: var(--text-main);
            border-color: var(--accent);
        }}
        .pulse-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            font-size: 0.75rem;
            color: var(--success);
            background: var(--success-glow);
            padding: 0.25rem 0.6rem;
            border-radius: 9999px;
            border: 1px solid rgba(16, 185, 129, 0.4);
        }}
        .pulse-dot {{
            width: 8px;
            height: 8px;
            background: var(--success);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0% {{ transform: scale(0.95); opacity: 0.8; }}
            50% {{ transform: scale(1.3); opacity: 1; }}
            100% {{ transform: scale(0.95); opacity: 0.8; }}
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2.25rem;
        }}
        .metric-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}
        .metric-card:hover {{
            transform: translateY(-2px);
            border-color: rgba(56, 189, 248, 0.4);
        }}
        .metric-title {{
            font-size: 0.85rem;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.6rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .metric-value {{
            font-size: 2.75rem;
            font-weight: 800;
            line-height: 1;
            margin-bottom: 0.4rem;
        }}
        .card-total .metric-value {{ color: var(--accent); }}
        .card-success .metric-value {{ color: var(--success); }}
        .card-failed .metric-value {{ color: var(--failed); }}
        .metric-footer {{
            font-size: 0.8rem;
            color: var(--text-muted);
        }}
        .table-section-title {{
            font-size: 1.1rem;
            font-weight: 700;
            margin-bottom: 0.9rem;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .table-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.9rem;
        }}
        th {{
            background: #0d1424;
            color: var(--text-muted);
            padding: 0.85rem 1rem;
            font-weight: 600;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            border-bottom: 1px solid var(--border);
        }}
        td {{
            padding: 0.85rem 1rem;
            border-bottom: 1px solid var(--border);
            vertical-align: middle;
        }}
        tr:last-child td {{
            border-bottom: none;
        }}
        tr:hover td {{
            background-color: rgba(255, 255, 255, 0.02);
        }}
        .font-mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }}
        .time-cell {{ font-size: 0.82rem; color: var(--text-muted); white-space: nowrap; }}
        .reason-cell {{ font-size: 0.85rem; color: #cbd5e1; max-width: 320px; }}
        .empty-state {{ text-align: center; padding: 3rem; color: var(--text-muted); font-style: italic; }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.55rem;
            border-radius: 9999px;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }}
        .badge-success {{ background: var(--success-glow); color: #6ee7b7; border: 1px solid rgba(16, 185, 129, 0.4); }}
        .badge-failed {{ background: var(--failed-glow); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.4); }}
        .badge-browser {{ background: rgba(56, 189, 248, 0.15); color: #7dd3fc; border: 1px solid rgba(56, 189, 248, 0.4); }}
        .badge-sip {{ background: rgba(168, 85, 247, 0.15); color: #d8b4fe; border: 1px solid rgba(168, 85, 247, 0.4); }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <div class="brand-title">📊 FinSaathi Call Analytics</div>
                <div class="brand-sub">Real-Time Persistent Call Intelligence &bull; Day 8 LiveKit & Murf Voice Agent</div>
            </div>
            <div class="nav-links">
                <div class="pulse-badge">
                    <span class="pulse-dot"></span>
                    <span>Live Auto-Poll (3s)</span>
                </div>
                <a href="/dashboard" class="nav-tab active">Call Analytics</a>
                <a href="/escalations" class="nav-tab">🛡️ Escalations</a>
            </div>
        </header>

        <main>
            <div class="metrics-grid">
                <div class="metric-card card-total">
                    <div class="metric-title">
                        <span>Total Calls</span>
                        <span>📞</span>
                    </div>
                    <div class="metric-value" id="val-total">{total_calls}</div>
                    <div class="metric-footer">Total voice sessions initiated</div>
                </div>

                <div class="metric-card card-success">
                    <div class="metric-title">
                        <span>Successful Calls</span>
                        <span>✅</span>
                    </div>
                    <div class="metric-value" id="val-success">{successful_calls}</div>
                    <div class="metric-footer">Meaningful interactions ({rate}% success rate)</div>
                </div>

                <div class="metric-card card-failed">
                    <div class="metric-title">
                        <span>Failed Calls</span>
                        <span>⚠️</span>
                    </div>
                    <div class="metric-value" id="val-failed">{failed_calls}</div>
                    <div class="metric-footer">Disconnected before interaction completed</div>
                </div>
            </div>

            <div class="table-section-title">
                <span>Recent Call Records</span>
            </div>

            <div class="table-card">
                <table>
                    <thead>
                        <tr>
                            <th>Call ID</th>
                            <th>Started At</th>
                            <th>Channel</th>
                            <th>Duration</th>
                            <th>Outcome</th>
                            <th>Reason / Details</th>
                        </tr>
                    </thead>
                    <tbody id="table-body">
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </main>
    </div>

    <script>
        async function refreshAnalytics() {{
            try {{
                const res = await fetch('/api/calls', {{ cache: 'no-store' }});
                if (!res.ok) return;
                const data = await res.json();

                document.getElementById('val-total').textContent = data.total_calls;
                document.getElementById('val-success').textContent = data.successful_calls;
                document.getElementById('val-failed').textContent = data.failed_calls;

                const tbody = document.getElementById('table-body');
                if (!data.recent_calls || data.recent_calls.length === 0) {{
                    tbody.innerHTML = `
                    <tr id="empty-row">
                        <td colspan="6" class="empty-state">
                            No call records recorded yet. Start a real voice session to see live analytics.
                        </td>
                    </tr>`;
                }} else {{
                    let rows = '';
                    for (const call of data.recent_calls) {{
                        const dur = Number(call.duration_seconds || 0);
                        const mins = Math.floor(dur / 60).toString().padStart(2, '0');
                        const secs = (dur % 60).toString().padStart(2, '0');
                        const durStr = `${{mins}}:${{secs}}`;

                        const channel = (call.channel || 'browser').toUpperCase();
                        const channelCls = channel.includes('SIP') ? 'badge-sip' : 'badge-browser';

                        const outcome = (call.outcome || 'failed').toUpperCase();
                        const outcomeCls = outcome === 'SUCCESS' ? 'badge-success' : 'badge-failed';

                        const reason = (outcome === 'SUCCESS' ? call.success_reason : call.failure_reason) || '-';

                        rows += `
                        <tr>
                            <td class="font-mono"><strong>${{call.call_id}}</strong></td>
                            <td class="time-cell">${{call.started_at || ''}}</td>
                            <td><span class="badge ${{channelCls}}">${{channel}}</span></td>
                            <td class="font-mono">${{durStr}}</td>
                            <td><span class="badge ${{outcomeCls}}">${{outcome}}</span></td>
                            <td class="reason-cell">${{reason}}</td>
                        </tr>
                        `;
                    }}
                    tbody.innerHTML = rows;
                }}
            }} catch (err) {{
                console.error("Auto-poll analytics failed:", err);
            }}
        }}

        // Poll every 3 seconds for real-time live updates
        setInterval(refreshAnalytics, 3000);
    </script>
</body>
</html>
"""
        self._send_html_response(html_content)

    def _handle_html_escalations(self) -> None:
        escalations = get_all_escalations()

        rows_html = ""
        if not escalations:
            rows_html = """
            <tr>
                <td colspan="9" class="empty-state">
                    No escalation requests recorded yet.
                </td>
            </tr>
            """
        else:
            for esc in escalations:
                urgency = html.escape(str(esc.get("urgency", "medium")).lower())
                urgency_badge = (
                    f'<span class="badge badge-{urgency}">{urgency.upper()}</span>'
                )
                status = html.escape(str(esc.get("status", "open")).upper())
                status_badge = f'<span class="badge badge-status">{status}</span>'

                ref_id = html.escape(str(esc.get("reference_id", "")))
                caller = html.escape(str(esc.get("caller_name", "Unknown")))
                issue = html.escape(str(esc.get("issue_type", "")))
                summary = html.escape(str(esc.get("short_summary", "")))
                lang = html.escape(str(esc.get("caller_language", "English")))
                followup = html.escape(
                    str(esc.get("preferred_follow_up_method", "not specified"))
                )
                created = html.escape(str(esc.get("created_at", "")))

                rows_html += f"""
                <tr>
                    <td class="font-mono"><strong>{ref_id}</strong></td>
                    <td>{caller}</td>
                    <td><span class="issue-tag">{issue}</span></td>
                    <td class="summary-cell">{summary}</td>
                    <td>{urgency_badge}</td>
                    <td>{lang}</td>
                    <td>{followup}</td>
                    <td>{status_badge}</td>
                    <td class="time-cell">{created}</td>
                </tr>
                """

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FinSaathi Human Support Escalation Dashboard</title>
    <style>
        :root {{
            --bg: #0b0f19;
            --card-bg: #151d30;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --border: #22314e;
            --accent: #38bdf8;
            --high: #ef4444;
            --med: #f59e0b;
            --low: #10b981;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            padding: 2rem;
            line-height: 1.5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.25rem;
        }}
        .brand-title {{
            font-size: 1.75rem;
            font-weight: 700;
            color: var(--accent);
            display: flex;
            align-items: center;
            gap: 0.6rem;
        }}
        .brand-sub {{
            color: var(--text-muted);
            font-size: 0.85rem;
            margin-top: 0.25rem;
        }}
        .nav-links {{
            display: flex;
            gap: 0.75rem;
            align-items: center;
        }}
        .nav-tab {{
            padding: 0.45rem 0.9rem;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 600;
            text-decoration: none;
            color: var(--text-muted);
            background: var(--card-bg);
            border: 1px solid var(--border);
            transition: all 0.2s ease;
        }}
        .nav-tab.active {{
            background: var(--accent);
            color: #0b0f19;
            border-color: var(--accent);
        }}
        .nav-tab:hover:not(.active) {{
            color: var(--text-main);
            border-color: var(--accent);
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.9rem;
        }}
        th {{
            background: #0d1424;
            color: var(--text-muted);
            padding: 0.85rem 1rem;
            font-weight: 600;
            font-size: 0.8rem;
            text-transform: uppercase;
            border-bottom: 1px solid var(--border);
        }}
        td {{
            padding: 0.85rem 1rem;
            border-bottom: 1px solid var(--border);
            vertical-align: middle;
        }}
        tr:hover {{
            background-color: rgba(255, 255, 255, 0.02);
        }}
        .font-mono {{ font-family: ui-monospace, monospace; color: var(--accent); }}
        .summary-cell {{ max-width: 320px; }}
        .time-cell {{ font-size: 0.8rem; color: var(--text-muted); white-space: nowrap; }}
        .empty-state {{ text-align: center; padding: 3rem; color: var(--text-muted); font-style: italic; }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.55rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .badge-high {{ background: rgba(239, 68, 68, 0.2); color: #fca5a5; border: 1px solid var(--high); }}
        .badge-medium {{ background: rgba(245, 158, 11, 0.2); color: #fcd34d; border: 1px solid var(--med); }}
        .badge-low {{ background: rgba(16, 185, 129, 0.2); color: #6ee7b7; border: 1px solid var(--low); }}
        .badge-status {{ background: rgba(56, 189, 248, 0.2); color: #7dd3fc; border: 1px solid var(--accent); }}
        .issue-tag {{
            background: #22314e;
            padding: 0.15rem 0.45rem;
            border-radius: 4px;
            font-size: 0.8rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <div class="brand-title">🛡️ FinSaathi Escalation Hub</div>
                <div class="brand-sub">Human Support Escalation Records &bull; Day 7 LiveKit Voice Agent</div>
            </div>
            <div class="nav-links">
                <a href="/dashboard" class="nav-tab">📊 Call Analytics</a>
                <a href="/escalations" class="nav-tab active">🛡️ Escalations</a>
            </div>
        </header>

        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th>Reference ID</th>
                        <th>Caller</th>
                        <th>Issue Type</th>
                        <th>Short Summary</th>
                        <th>Urgency</th>
                        <th>Language</th>
                        <th>Follow-up</th>
                        <th>Status</th>
                        <th>Created At</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""
        self._send_html_response(html_content)

    def log_message(self, format_str: str, *args: object) -> None:
        logger.info(
            "%s - - [%s] %s",
            self.address_string(),
            self.log_date_time_string(),
            format_str % args,
        )


def run_dashboard_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    init_analytics_db()
    init_escalations_db()
    server_address = (host, port)
    httpd = HTTPServer(server_address, UnifiedDashboardHandler)
    print(f"FinSaathi Analytics Dashboard running at http://{host}:{port}/dashboard")
    print(f"FinSaathi Escalations Hub running at http://{host}:{port}/escalations")
    print(f"JSON Analytics API available at http://{host}:{port}/api/analytics")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server.")
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FinSaathi Unified Call Analytics & Escalation Dashboard"
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port number (default: 8080)"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    run_dashboard_server(host=args.host, port=args.port)

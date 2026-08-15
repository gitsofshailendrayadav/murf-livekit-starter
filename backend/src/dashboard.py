from __future__ import annotations

import argparse
import html
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    from escalation import get_all_escalations, init_escalations_db
except ImportError:
    from src.escalation import get_all_escalations, init_escalations_db

logger = logging.getLogger("dashboard")


class EscalationsDashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/api/escalations", "/escalations/json"):
            self._handle_api_escalations()
        elif self.path in ("/", "/escalations", "/dashboard"):
            self._handle_html_dashboard()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Page not found")

    def _handle_api_escalations(self) -> None:
        escalations = get_all_escalations()
        payload = json.dumps(
            {"escalations": escalations, "count": len(escalations)}, indent=2
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _handle_html_dashboard(self) -> None:
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
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --border: #334155;
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
            padding-bottom: 1rem;
        }}
        h1 {{
            font-size: 1.75rem;
            color: var(--accent);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .stats {{
            display: flex;
            gap: 1rem;
        }}
        .stat-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.5rem 1rem;
            text-align: center;
        }}
        .stat-val {{ font-size: 1.25rem; font-weight: bold; color: var(--accent); }}
        .stat-label {{ font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.9rem;
        }}
        th {{
            background: #0b1120;
            color: var(--text-muted);
            padding: 0.85rem 1rem;
            font-weight: 600;
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
            background: #334155;
            padding: 0.15rem 0.45rem;
            border-radius: 4px;
            font-size: 0.8rem;
        }}
        .refresh-btn {{
            background: var(--accent);
            color: #0f172a;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            font-weight: bold;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
        }}
        .refresh-btn:hover {{ opacity: 0.9; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>🛡️ FinSaathi Human Support Dashboard</h1>
                <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.25rem;">
                    Local Escalation Hub &bull; Day 7 Murf AI Voice Agent Challenge
                </p>
            </div>
            <div style="display: flex; gap: 1rem; align-items: center;">
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-val">{len(escalations)}</div>
                        <div class="stat-label">Total Requests</div>
                    </div>
                </div>
                <a href="/escalations" class="refresh-btn">↻ Refresh</a>
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
        payload = html_content.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format_str: str, *args: object) -> None:
        logger.info(
            "%s - - [%s] %s",
            self.address_string(),
            self.log_date_time_string(),
            format_str % args,
        )


def run_dashboard_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    init_escalations_db()
    server_address = (host, port)
    httpd = HTTPServer(server_address, EscalationsDashboardHandler)
    print(f"FinSaathi Escalation Dashboard running at http://{host}:{port}/escalations")
    print(f"JSON API available at http://{host}:{port}/api/escalations")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server.")
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FinSaathi Human Support Escalation Dashboard"
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

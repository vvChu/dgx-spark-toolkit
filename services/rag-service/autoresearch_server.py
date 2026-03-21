#!/usr/bin/env python3
"""Autoresearch HTTP Server — lightweight standalone server for experiments.

Runs on port 8099 inside the container (mapped to host via Docker).
Provides endpoints to run audit, apply/revert pipeline fixes.

Start: python3 autoresearch_server.py &
"""

import http.server
import json
import subprocess
import sys
import os
import time
import re
from urllib.parse import urlparse, parse_qs

PORT = 8099


class AutoresearchHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/audit":
            self._run_audit()
        elif path == "/pipeline/apply":
            self._run_pipeline("--apply")
        elif path == "/pipeline/revert":
            self._run_pipeline("--revert")
        elif path == "/pipeline/dry-run":
            self._run_pipeline("--dry-run")
        elif path == "/experiment":
            desc = params.get("desc", ["unnamed"])[0]
            self._run_experiment(desc)
        elif path == "/health":
            self._respond(200, {"status": "ok", "service": "autoresearch"})
        else:
            self._respond(404, {"error": "Unknown endpoint. Use /audit, /pipeline/{apply|revert|dry-run}, /experiment?desc=..."})

    def _run_audit(self):
        """Run comprehensive_audit.py and return raw output."""
        try:
            start = time.time()
            result = subprocess.run(
                [sys.executable, "/app/comprehensive_audit.py"],
                capture_output=True, text=True, timeout=300,
                cwd="/app",
            )
            elapsed = time.time() - start
            output = result.stdout + result.stderr

            # Parse scores
            scores = self._parse_scores(output)
            scores["time_sec"] = round(elapsed, 1)

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            
            # Append JSON summary at the end for machine parsing
            self.wfile.write(output.encode("utf-8"))
            self.wfile.write(b"\n\n--- PARSED SCORES ---\n")
            self.wfile.write(json.dumps(scores, indent=2, ensure_ascii=False).encode("utf-8"))
        except subprocess.TimeoutExpired:
            self._respond(504, {"error": "Audit timed out (>300s)"})
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _run_pipeline(self, action: str):
        """Run pipeline.py with the given action."""
        try:
            result = subprocess.run(
                [sys.executable, "/app/pipeline.py", action],
                capture_output=True, text=True, timeout=120,
                cwd="/app",
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write((result.stdout + result.stderr).encode("utf-8"))
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _run_experiment(self, desc: str):
        """Full experiment cycle: revert → apply → audit."""
        try:
            output_parts = []

            # Step 1: Revert to baseline
            output_parts.append("=== STEP 1: Revert to baseline ===")
            r = subprocess.run(
                [sys.executable, "/app/pipeline.py", "--revert"],
                capture_output=True, text=True, timeout=60, cwd="/app",
            )
            output_parts.append(r.stdout + r.stderr)

            # Step 2: Apply current fixes
            output_parts.append("\n=== STEP 2: Apply pipeline.py fixes ===")
            r = subprocess.run(
                [sys.executable, "/app/pipeline.py", "--apply"],
                capture_output=True, text=True, timeout=120, cwd="/app",
            )
            output_parts.append(r.stdout + r.stderr)

            # Step 3: Run audit
            output_parts.append("\n=== STEP 3: Run comprehensive audit ===")
            start = time.time()
            r = subprocess.run(
                [sys.executable, "/app/comprehensive_audit.py"],
                capture_output=True, text=True, timeout=300, cwd="/app",
            )
            elapsed = time.time() - start
            audit_output = r.stdout + r.stderr
            output_parts.append(audit_output)

            # Parse scores
            scores = self._parse_scores(audit_output)
            scores["time_sec"] = round(elapsed, 1)
            scores["experiment"] = desc

            output_parts.append(f"\n=== PARSED SCORES ===")
            output_parts.append(json.dumps(scores, indent=2, ensure_ascii=False))

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("\n".join(output_parts).encode("utf-8"))
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _parse_scores(self, output: str) -> dict:
        """Parse audit output into scores dict."""
        scores = {}
        patterns = {
            "A_markdown": r"MARKDOWN SCORE:\s*(\d+)/100",
            "B_json": r"JSON EXPORT SCORE:\s*(\d+)/100",
            "C_chunking": r"CHUNKING SCORE:\s*(\d+)/100",
            "D_milvus": r"MILVUS INGESTION SCORE:\s*(\d+)/100",
            "E_fidelity": r"FIDELITY SCORE:\s*(\d+)/100",
            "overall": r"OVERALL QUALITY SCORE:\s*(\d+)/100",
        }
        for key, pattern in patterns.items():
            m = re.search(pattern, output)
            if m:
                scores[key] = int(m.group(1))

        # P-issue indicators
        p = {}
        m = re.search(r"broken_table\s*:\s*(\d+)/(\d+)", output)
        if m: p["P1_broken_table"] = f"{m.group(1)}/{m.group(2)}"
        m = re.search(r"ai_leakage\s*:\s*(\d+)/(\d+)", output)
        if m: p["P2_ai_leakage"] = f"{m.group(1)}/{m.group(2)}"
        m = re.search(r"Article strategy rate\s*:\s*([\d.]+)%", output)
        if m: p["P3_article_rate"] = f"{m.group(1)}%"
        m = re.search(r"Missing doc_number\s*:\s*(\d+)/(\d+)", output)
        if m: p["P4_missing_docnum"] = f"{m.group(1)}/{m.group(2)}"
        m = re.search(r"boilerplate\s*:\s*(\d+)/(\d+)", output)
        if m: p["P5_boilerplate"] = f"{m.group(1)}/{m.group(2)}"
        m = re.search(r"Child/Parent ratio\s*:\s*([\d.]+)", output)
        if m: p["P6_child_parent"] = m.group(1)
        m = re.search(r"AI monologue leakage\s*:\s*(\d+)/(\d+)", output)
        if m: p["P2_ai_leakage_milvus"] = f"{m.group(1)}/{m.group(2)}"
        scores["p_issues"] = p
        return scores

    def _respond(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress default logging


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", PORT), AutoresearchHandler)
    print(f"Autoresearch server running on port {PORT}")
    print(f"  /audit          — Run comprehensive audit")
    print(f"  /pipeline/apply — Apply fixes")
    print(f"  /pipeline/revert — Revert to backup")
    print(f"  /experiment?desc=NAME — Full experiment cycle")
    server.serve_forever()

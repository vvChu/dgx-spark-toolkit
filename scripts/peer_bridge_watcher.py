#!/usr/bin/env python3
"""
Peer Agent Bridge Watcher: Antigravity <-> Grok
Theo doi va dong bo hoa tu dong giua Antigravity va Grok tren cung workspace.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
PEER_EXCHANGE_DIR = WORKSPACE_DIR / ".md" / "peer_exchange"
GROK_SESSIONS_BASE = Path("/home/vvc/.grok/sessions/%2Fhome%2Fvvc%2FCodebase%2Fdgx-spark-toolkit")
REPORT_PATH = WORKSPACE_DIR / "docs" / "architecture_audit_report.md"


def get_latest_grok_session() -> Optional[Path]:
    """Tim thu muc session chinh cua Grok (co chua workflows)."""
    if not GROK_SESSIONS_BASE.exists():
        return None
    sessions = [
        d for d in GROK_SESSIONS_BASE.iterdir()
        if d.is_dir() and (d / "workflows").exists()
    ]
    if not sessions:
        # Fallback neu chua co workflows
        sessions = [
            d for d in GROK_SESSIONS_BASE.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
    if not sessions:
        return None
    sessions.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return sessions[0]


def parse_grok_workflow(session_dir: Path) -> Dict[str, Any]:
    """Phan tich trang thai workflow va subagents cua Grok."""
    result: Dict[str, Any] = {
        "session_id": session_dir.name,
        "workflow_id": None,
        "current_phase": "unknown",
        "status": "idle",
        "agents": [],
        "findings": [],
    }

    workflows_dir = session_dir / "workflows"
    if not workflows_dir.exists():
        return result

    # Lay workflow moi nhat
    wf_dirs = [d for d in workflows_dir.iterdir() if d.is_dir()]
    if not wf_dirs:
        return result
    wf_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    wf_dir = wf_dirs[0]
    result["workflow_id"] = wf_dir.name

    state_file = wf_dir / "state.json"
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            st = state_data.get("state", {})
            result["current_phase"] = st.get("current_phase", "unknown")
            result["status"] = st.get("status", "unknown")
            result["agents"] = st.get("agents", [])
        except Exception as e:
            result["error_reading_state"] = str(e)

    # Doc findings tu subagents da hoan thanh
    subagents_dir = session_dir / "subagents"
    if subagents_dir.exists():
        for agent_dir in sorted(subagents_dir.iterdir(), key=lambda x: x.name):
            if not agent_dir.is_dir():
                continue
            output_file = agent_dir / "output.json"
            if output_file.exists():
                try:
                    with open(output_file, "r", encoding="utf-8") as f:
                        out_data = json.load(f)
                    output_text = out_data.get("output", "")
                    meta_file = agent_dir / "meta.json"
                    label = agent_dir.name
                    if meta_file.exists():
                        try:
                            with open(meta_file, "r", encoding="utf-8") as mf:
                                meta_data = json.load(mf)
                                label = meta_data.get("label", label)
                        except Exception:
                            pass
                    result["findings"].append({
                        "agent_id": agent_dir.name,
                        "label": label,
                        "raw_output": output_text
                    })
                except Exception:
                    pass

    return result


def sync_peer_exchange(info: Dict[str, Any]) -> None:
    """Cap nhat trang thai sang thu muc .md/peer_exchange/."""
    PEER_EXCHANGE_DIR.mkdir(parents=True, exist_ok=True)

    has_report = REPORT_PATH.exists()
    status_summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "peers": {
            "antigravity": {
                "name": "Antigravity (Pair Architect)",
                "plan_path": "/home/vvc/.gemini/antigravity/brain/be0a11ab-f001-4bd6-99fa-0910bbea473d/implementation_plan.md",
                "status": "ready"
            },
            "grok": {
                "name": "Grok 4.7 xhigh (Auditor)",
                "session_id": info["session_id"],
                "workflow_id": info["workflow_id"],
                "current_phase": info["current_phase"],
                "status": info["status"],
                "agents_count": len(info["agents"]),
                "completed_findings_count": len(info["findings"]),
                "report_ready": has_report,
                "report_path": str(REPORT_PATH) if has_report else None
            }
        }
    }

    # Ghi status.json
    status_file = PEER_EXCHANGE_DIR / "status.json"
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(status_summary, f, indent=2, ensure_ascii=False)

    # Ghi grok_live_summary.md
    summary_md = PEER_EXCHANGE_DIR / "grok_live_summary.md"
    with open(summary_md, "w", encoding="utf-8") as f:
        f.write("# 📡 TỔNG HỢP TIẾN ĐỘ THỜI GIAN THỰC TỪ GROK\n\n")
        f.write(f"- **Cập nhật lúc**: `{status_summary['timestamp']}`\n")
        f.write(f"- **Session ID**: `{info['session_id']}`\n")
        f.write(f"- **Workflow ID**: `{info['workflow_id']}`\n")
        f.write(f"- **Giai đoạn hiện tại**: **`{info['current_phase']}`**\n")
        f.write(f"- **Trạng thái**: `{info['status']}`\n")
        f.write(f"- **Báo cáo cuối cùng (`docs/architecture_audit_report.md`)**: "
                f"{'✅ ĐÃ SẴN SÀNG' if has_report else '⏳ ĐANG XỬ LÝ'}\n\n")

        f.write("## 🤖 Tiến độ Subagents của Grok\n\n")
        f.write("| Subagent | Giai đoạn | Trạng thái | Tokens | Thời gian (ms) |\n")
        f.write("|---|---|---|---|---|\n")
        for ag in info["agents"]:
            f.write(f"| `{ag.get('label')}` | {ag.get('phase')} | **{ag.get('state')}** | "
                    f"{ag.get('tokens_used', 0):,} | {ag.get('duration_ms', 0):,} |\n")

        f.write("\n## 🔍 Các phát hiện cốt lõi từ Grok đã thu thập được\n\n")
        if not info["findings"]:
            f.write("_Chưa có subagent nào hoàn tất output._\n")
        else:
            for item in info["findings"]:
                f.write(f"### Subagent: `{item['label']}` (`{item['agent_id'][:8]}`)\n\n")
                f.write(f"{item['raw_output']}\n\n---\n\n")


def main() -> int:
    mode = "--once"
    if len(sys.argv) > 1:
        mode = sys.argv[1]

    session_dir = get_latest_grok_session()
    if not session_dir:
        print("[ERR] Khong tim thay session Grok nao.")
        return 1

    if mode == "--once":
        info = parse_grok_workflow(session_dir)
        sync_peer_exchange(info)
        print(f"[OK] Da dong bo thanh cong voi phien Grok: {info['session_id']}")
        print(f"     Phase: {info['current_phase']} | Subagents: {len(info['agents'])} | "
              f"Findings: {len(info['findings'])}")
        return 0
    elif mode == "--watch":
        print(f"[WATCH] Bat dau giam sat lien tuc phien Grok: {session_dir.name}...")
        try:
            while True:
                info = parse_grok_workflow(session_dir)
                sync_peer_exchange(info)
                if REPORT_PATH.exists() and info["current_phase"] in ("Confirm", "Repair", "done"):
                    print("[DONE] Grok da hoan tat toan bo workflow va xuat bao cao!")
                    break
                time.sleep(5)
        except KeyboardInterrupt:
            print("\n[STOP] Da dung giam sat.")
        return 0
    else:
        print("Usage: peer_bridge_watcher.py [--once | --watch]")
        return 1


if __name__ == "__main__":
    sys.exit(main())

---
name: setup-remote
command: /setup-remote
description: Configure firewall and network for remote access to all AI services
type: workflow
category: custom
enabled: true
version: v3.0
---

1. Run the remote access setup script (requires sudo). This will configure firewall rules and identify the best IP (e.g. Tailscale) for connection:
```bash
sudo bash /home/vvc/Codebase/dgx-spark-toolkit/scripts/setup-remote-access.sh
```


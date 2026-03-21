---
name: update-qwen
command: /update-qwen
description: Update Qwen models to the latest versions
type: workflow
category: custom
enabled: true
version: v3.0
---
Trigger a manual image pull and container restart for the **rag-core** (Qwen 3.5 35B) model.
This workflow executes the `qwen-update.sh` script to pull the latest image and restart the model container, then verifies the operation.

1. Execute the update script
// turbo
```bash
bash /home/vvc/Codebase/dgx-spark-toolkit/scripts/qwen-update.sh
```

2. Check container status (rag-core)
// turbo
```bash
docker ps -f name=qwen35b
```

3. View recent logs to confirm the restart initiated successfully
// turbo
```bash
docker logs --tail 20 qwen35b
```

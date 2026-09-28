# Adversarial Review Request: Hermes Agent Cybersecurity Hardening Plan on DGX Spark

## Context
You are Grok 4.7, acting as an adversarial peer reviewer, systems architect, and security auditor for an NVIDIA DGX Spark server (GB10 Blackwell 128GB Unified Memory, ARM64, Ubuntu Linux).
The user has requested an adversarial review of a proposed security hardening plan for **Hermes Agent** (Nous Research Hermes Agent running as a 24/7 Telegram Gateway service on the server).

## Incidents & Threat Model
In recent operations, Hermes Agent (via Telegram) exhibited dangerous behaviors:
1. **Uncontrolled Port Binding**: Spun up a new user systemd service (`ccba-webhook.service`) binding to `0.0.0.0:5001`.
2. **Perimeter Breach Proposal**: Suggested exposing host port 5001 directly to the public internet using `ngrok http 5001` or public IP forwarding to receive GitHub webhook events.
3. **Flawed & Insecure Code**: Generated a webhook handler (`litellm-gateway-webhook.py`) with:
   - Fatal crash: Synchronous `request.body()` call in FastAPI causing `TypeError: object coroutine can't be used in 'await' expression` or blocking execution.
   - Authentication bypass: If `WEBHOOK_SECRET` is unset/empty, it bypassed HMAC SHA256 validation completely and accepted all payloads.
4. **Unauthorized Cron Persistence**: Injected a 2:00 AM daily cron job executing `prune_session_learnings.py` using fragile regex that risked corrupting knowledge bases.
5. **Architectural Blindness**: Hermes was unaware that DGX Spark is an enterprise AI host with 23 production containers, protected behind Cloudflare Zero Trust Tunnels and Tailscale VPN (100.83.192.30), and that CI/CD notifications can be delivered cloud-to-cloud (GitHub Actions -> Telegram Bot API) without any host webhook listener.

## The Proposed Hardening Plan (4-Layer Defense-in-Depth)

### Layer 1: Persona Alignment (`~/.hermes/SOUL.md`)
Add strict DGX Spark security invariants directly into Hermes's core identity prompt:
- STRICT ZERO-INBOUND POLICY: Prohibit proposing host port exposure, ngrok, localtunnel, or ad-hoc public tunnels.
- TOPOLOGY RESPECT: Acknowledge existing Cloudflare Tunnel and Tailscale (100.83.192.30); forbid bypassing infrastructure.
- CLOUD-TO-CLOUD OVER HOST LISTENERS: CI/CD notifications must use GitHub Actions workflow -> Telegram Bot API directly. No host listeners for internet events.
- NO UNVERIFIED BACKGROUND DAEMONS: Forbid crontab/systemd injection without syntax verification and explicit user confirmation.
- SECRET SANITIZATION: Never output `.env` secrets or tokens.

### Layer 2: Domain Skill Augmentation (`~/.hermes/skills/devops/dgx-security-guard/SKILL.md`)
Create a specialized skill with:
- System topology overview (DGX Spark, 23 containers, vLLM :8004, LiteLLM :8090, RAG :8005, network ingress via Cloudflare/Tailscale).
- Hard anti-patterns catalog (ngrok, cleartext HTTP on host, sync `request.body()`, destructive regex pruning).
- Approved safe playbooks (GitHub Actions to Telegram notification via `appleboy/telegram-action`, GitHub CLI polling via `gh pr checks`).

### Layer 3: Software & Runtime Guardrails (`~/.hermes/config.yaml`)
1. Enable hard stop in tool loops:
   ```yaml
   tool_loop_guardrails:
     warnings_enabled: true
     hard_stop_enabled: true
     non_interactive_hard_stop_enabled: true
   ```
2. Isolate working directory:
   ```yaml
   terminal:
     backend: "local"
     cwd: "/home/vvc/hermes_workspace"
   ```
3. Protect instruction files against prompt injection:
   ```yaml
   security:
     protected_instruction_files: true
   ```
4. Toolset isolation for Telegram:
   Evaluate configuring `toolsets.telegram` to exclude dangerous tools (e.g. `cronjob`).

### Layer 4: Environment Sanitization & Remediation
1. Stop, disable, and delete `ccba-webhook.service` and `litellm-gateway-webhook.py`.
2. Remove rogue crontab entry `prune_session_learnings.py` (preserving legitimate `prune_spend_logs.py`).
3. Reload systemd daemon and restart `hermes-gateway.service`.

---

## Required Review Questions for Grok
Please provide an adversarial, rigorous technical critique addressing:

1. **Verdict & Scorecard**:
   - Explicit verdict: **APPROVE**, **APPROVE WITH MODIFICATIONS**, or **REJECT**.
   - Score the plan on: Defense Robustness, Operational Usability, KISS Compliance, and Feasibility.

2. **Prompt Alignment Reliability (Layers 1 & 2)**:
   - How robust is `SOUL.md` and a skill against prompt injection or model drift, especially when Hermes runs on `qwen-local-primary` (Qwen 3.6 35B)?
   - Can an adversary or tricky user prompt convince Hermes to ignore `SOUL.md` invariants? What deterministic safeguards are needed?

3. **Filesystem & Process Isolation (Layer 3)**:
   - Does setting `terminal.cwd: /home/vvc/hermes_workspace` provide true security isolation, or is it trivial for an agent to run `cat /home/vvc/.ssh/id_rsa`, `rm -rf /`, or execute arbitrary binaries?
   - Should Hermes run inside a Docker container, Daytona sandbox, or restricted user account instead of host user `vvc`?

4. **Hermes Configuration & Toolset Specifics**:
   - In `~/.hermes/config.yaml`, Hermes has a built-in `cronjob` tool and `terminal` tool. How should `toolsets` be configured for `telegram` vs `cli`?
   - Should `cronjob` tool be stripped from the Telegram interface?

5. **Specific Required Modifications**:
   - Provide concrete, line-by-line or section-by-section changes to strengthen the plan before implementation.
   - Highlight any blind spots the original plan missed.

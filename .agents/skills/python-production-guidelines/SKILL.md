---
name: python-production-guidelines
description: Core architectural and operational guidelines for Python, FastAPI, and RAG systems (High Concurrency & Stability).
---

# Python Production Guidelines

These are the 5 core architectural guidelines derived from real-world, high-concurrency production deployments (specifically on systems like DGX Spark Toolkit). When writing or refactoring Python code, especially for FastAPI and RAG applications, you MUST adhere to these rules:

## 1. Resource Management (Connection Pooling & Leaks)
- **Rule**: NEVER instantiate heavy resources (HTTP Clients, Database Drivers) inside every function call.
- **Why**: Creating `httpx.Client`, `httpx.AsyncClient`, or `GraphDatabase.driver` on every request exhausts TCP connection ports and wastes CPU/Latency on TLS handshakes.
- **Pattern**: Use the Singleton pattern (with threading/async locks) at the module level, or attach resources to the application lifecycle (e.g., FastAPI `lifespan` or long-lived class instances).
- **Cleanup**: ALWAYS provide and use an explicit `.close()` or `await .aclose()` method to clean up resources during graceful shutdowns or error recoveries (using `try/finally` blocks).

## 2. Thread-Safety with C/C++ Bindings (e.g., PyMuPDF)
- **Rule**: Objects wrapping C/C++ memory architectures (like `fitz.Document` from PyMuPDF) are often absolutely **NOT thread-safe**, even for read-only operations.
- **Why**: Sharing a single `fitz.Document` instance across multiple worker threads can lead to Segmentation Faults, core dumps, corrupted parsed data, or silent crashes.
- **Pattern**: Each worker thread or parallel process MUST independently open its own instance of the file (e.g., `fitz.open(file_path)`) and close it when done.

## 3. Event Loop Traps with `asyncio.Lock`
- **Rule**: NEVER declare `lock = asyncio.Lock()` at the top (module) level of a Python file.
- **Why**: `asyncio.Lock` binds to the event loop running at the exact moment of initialization. If initialized at import time, it will bind to the wrong loop (or none at all). When later awaited inside an active application loop, it raises `"Task got bad yield"` or `"Future belongs to a different loop"`.
- **Pattern**: Use **Lazy Initialization**. Declare a module-level variable as `None`, and initialize the lock inside the first async function call, checking if it is `None` under a standard synchronous `threading.Lock()` if necessary, or simply lazily instantiating it within the running event loop.

## 4. Asynchronous Traps in Event Watchers (Watchdog)
- **Rule**: NEVER use blocking logic like `time.sleep()` or heavy network/I-O calls directly inside file system event hooks like `on_created()`.
- **Why**: Libraries like `watchdog` dispatch events on their own internal observer thread. Blocking this thread "deafens" the system; subsequent file system events during the sleep period will be queued up or entirely dropped.
- **Pattern**: The handler should immediately offload work to a separate daemon thread or an asynchronous queue, and explicitly return. 
  - *Example*: `threading.Thread(target=process_file, args=(event.src_path,), daemon=True).start()`

## 5. Safe PostgreSQL Interval Arithmetic
- **Rule**: Avoid non-portable SQL parameter bindings for intervals like `:stale_minutes * INTERVAL '1 minute'`.
- **Why**: While this syntax may work in some modern PostgreSQL versions, it is notoriously fragile across different ORMs and drivers (`psycopg2`, `asyncpg`), often failing silently or throwing type inference errors when the parameter is treated as an integer rather than numeric.
- **Pattern**: Use explicit, robust functions like `make_interval(mins => :stale_minutes)` to ensure 100% compatibility and safety across all driver versions. 

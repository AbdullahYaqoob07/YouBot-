"""
Gunicorn Configuration for Production Deployment (Ubuntu Optimized)

Usage:
    gunicorn app:app -c gunicorn.conf.py

Features:
    - Preload app to share embeddings across workers
    - Graceful worker recycling
    - Optimized for AI/ML workloads with heavy initialization
    - Ubuntu production settings
"""

import os
import multiprocessing

# Server Socket
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
backlog = 2048

# Worker Processes
# For ML workloads, fewer workers with more threads is better
# Each worker loads embeddings once due to preload
# Ubuntu: Use CPU count but cap at 4 for memory efficiency
cpu_count = multiprocessing.cpu_count()
workers = int(os.getenv("GUNICORN_WORKERS", min(cpu_count, 4)))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000

# Timeouts - Optimized for production
timeout = 30  # Reduced from 120 - fail fast for slow requests
keepalive = 65  # Increased for HTTP/1.1 persistent connections (slightly > nginx default 60)
graceful_timeout = 30

# CRITICAL: Preload app to share heavy resources (embeddings) across workers
# This loads the app ONCE in the master process, then forks workers
# All workers share the same embeddings in memory (copy-on-write)
preload_app = True

# Worker Recycling (prevents memory leaks)
max_requests = 1000
max_requests_jitter = 100  # Spread restarts to avoid thundering herd

# Request Limits
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Logging
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")  # stdout or file
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")   # stderr or file
loglevel = os.getenv("LOG_LEVEL", "info").lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sμs'

# Process Naming
proc_name = "sweden-relocators-ai"

# Server Mechanics
daemon = False
pidfile = os.getenv("GUNICORN_PID_FILE", None)
umask = 0o022  # More restrictive file permissions
user = os.getenv("GUNICORN_USER", None)  # Run as specific user in production
group = os.getenv("GUNICORN_GROUP", None)
tmp_upload_dir = None

# Performance Tuning for Ubuntu
# These environment variables can be set for additional optimization:
# - MALLOC_ARENA_MAX=2 (reduce memory fragmentation)
# - PYTHONUNBUFFERED=1 (unbuffered output for logging)
# - PYTHONDONTWRITEBYTECODE=1 (no .pyc files)

# Hooks for lifecycle management
def on_starting(server):
    """Called just before the master process is initialized."""
    print("🚀 Starting Sweden Relocators AI Agent...")
    print(f"   Workers: {workers} (CPU cores: {cpu_count})")
    print(f"   Preload: {preload_app}")
    print(f"   Bind: {bind}")
    print(f"   Timeout: {timeout}s")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    print(f"   Worker {worker.pid} spawned")

def post_worker_init(worker):
    """Called just after a worker has initialized the application."""
    print(f"   Worker {worker.pid} ready")

def worker_int(worker):
    """Called when a worker receives SIGINT or SIGQUIT."""
    print(f"   Worker {worker.pid} interrupted")

def worker_abort(worker):
    """Called when a worker receives SIGABRT."""
    print(f"   Worker {worker.pid} aborted")

def pre_exec(server):
    """Called just before a new master process is forked."""
    print("   Forking new master process...")

def when_ready(server):
    """Called just after the server is started."""
    print("✅ Server is ready to accept connections!")
    print(f"   API: http://{bind}")
    print(f"   Health: http://{bind}/health")
    print(f"   Metrics: http://{bind}/metrics")

def on_exit(server):
    """Called just before exiting Gunicorn."""
    print("👋 Shutting down Sweden Relocators AI Agent...")

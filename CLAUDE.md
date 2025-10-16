# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bandwidth Tester (带宽测试器) - A Python-based multi-threaded download tool for network bandwidth testing. The application is containerized with Docker and supports multi-architecture deployment (amd64/arm64).

**Core Purpose**: Network performance testing and bandwidth stress testing using concurrent HTTP downloads.

## Architecture

### Single-File Application Design
The entire application logic is contained in `bandwidth_tester.py` (~236 lines). This is intentional for simplicity and ease of deployment.

**Key Components**:

1. **ThreadSafeStats Class** (lines 37-77)
   - Manages shared state across threads using `threading.Lock`
   - Tracks: `_bytes_downloaded`, `_running_threads`
   - **Critical**: All state modifications MUST go through this class to prevent race conditions

2. **Global State Management**
   - `stats` (ThreadSafeStats instance) - Thread-safe statistics
   - `shutdown_event` (threading.Event) - Graceful shutdown coordination
   - `executor` (ThreadPoolExecutor) - Thread pool management
   - `session` (requests.Session) - HTTP connection pooling

3. **Concurrency Pattern**
   - Main loop monitors thread count and replenishes completed threads
   - Each worker thread runs `download()` function independently
   - Uses `threading.Event` for inter-thread communication, not boolean flags
   - Connection pool size: `max(thread_count * 2, 20)`

### Thread Safety Requirements

**IMPORTANT**: When modifying state-related code:
- Never use direct variable assignment for shared state
- Always use ThreadSafeStats methods: `add_bytes()`, `increment_running()`, etc.
- Use `shutdown_event.is_set()` and `shutdown_event.set()` instead of boolean flags
- Initialize variables that might be used in `finally` blocks (see line 117)

### Configuration System

All configuration is environment variable-based:
- `THREAD_COUNT` (default: 5) - Number of concurrent download threads
- `GOAL_GB` (default: 0) - Target traffic in GB (0 = unlimited)
- `URL_LIST` (default: 7 CDN URLs) - Comma-separated download URLs

Environment variables are read once at startup (lines 27-33) and converted to appropriate types immediately.

## Development Commands

### Local Development (Non-Docker)

```bash
# Install dependencies
pip install -r requirements.txt

# Run with defaults (5 threads, unlimited traffic)
python3 bandwidth_tester.py

# Run with custom configuration
THREAD_COUNT=10 GOAL_GB=5 python3 bandwidth_tester.py
```

### Docker Development

```bash
# Build local image
docker build -t bandwidth-tester:latest .

# Test locally
docker run --rm -e THREAD_COUNT=3 -e GOAL_GB=1 bandwidth-tester:latest

# View logs
docker logs -f bandwidth-tester
```

### Docker Compose

```bash
# Start with defaults
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## Multi-Architecture Build & Deployment

**CRITICAL**: This project supports both amd64 and arm64. Always build multi-arch images.

```bash
# Create/use buildx builder (one-time setup)
docker buildx create --name multiarch --use || docker buildx use multiarch

# Build and push multi-architecture images
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag goushuai888/bandwidth-tester:v1.0.1 \
  --tag goushuai888/bandwidth-tester:latest \
  --push \
  .

# Push to GitHub Container Registry
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag ghcr.io/goushuai888/bandwidth-tester:v1.0.1 \
  --tag ghcr.io/goushuai888/bandwidth-tester:latest \
  --push \
  .

# Verify multi-arch manifest
docker buildx imagetools inspect goushuai888/bandwidth-tester:latest
```

**Publishing Locations**:
- Docker Hub: `goushuai888/bandwidth-tester`
- GitHub Container Registry: `ghcr.io/goushuai888/bandwidth-tester`

## Docker Security Configuration

The `docker-compose.yml` implements CIS Docker Benchmark security controls:

- `security_opt: [no-new-privileges:true]` - CIS 5.25
- `cap_drop: [ALL]` - CIS 5.3 (minimal capabilities)
- `read_only: true` - CIS 5.12 (immutable filesystem)
- `pids_limit: 100` - CIS 5.28 (fork bomb prevention)
- Non-root user (appuser, UID 1000)
- Resource limits (2 CPUs, 512M memory)

**When modifying docker-compose.yml**: Maintain these security settings unless there's a specific reason to change them.

## Code Modification Guidelines

### Adding New Features

1. **State Management**: If adding new shared state, extend `ThreadSafeStats` class
2. **Configuration**: Add new environment variables at the top with other config (lines 27-33)
3. **Thread Safety**: Use locks or thread-safe data structures for all shared data

### Common Pitfall: Race Conditions

❌ **Wrong** (causes race conditions):
```python
global counter
counter += 1
```

✅ **Correct** (thread-safe):
```python
stats.increment_running()
```

### Error Handling Pattern

The `download()` function demonstrates proper error handling (lines 148-164):
- Catch specific exceptions first (Timeout, ConnectionError)
- Generic RequestException for other HTTP errors
- Broad Exception catch for unexpected errors
- Always clean up in `finally` block with null checks

## Testing Considerations

**Manual Testing Checklist**:
1. Test graceful shutdown (Ctrl+C)
2. Test with GOAL_GB limit (verify it stops correctly)
3. Test with invalid URLs (verify error handling)
4. Test with THREAD_COUNT=1 (edge case)
5. Test in both Docker and non-Docker environments

**Load Testing**:
```bash
# High concurrency test
THREAD_COUNT=50 GOAL_GB=1 python3 bandwidth_tester.py

# Monitor thread safety with multiple short runs
for i in {1..10}; do GOAL_GB=0.1 python3 bandwidth_tester.py; done
```

## Performance Characteristics

- **Bottleneck**: Network bandwidth (I/O-bound, not CPU-bound)
- **Chunk Size**: 100KB (configurable in line 128)
- **Timeout**: (5s connect, 30s read) - see line 124
- **Check Interval**: 500ms main loop polling (line 205)

**Performance Tuning**:
- Increase `THREAD_COUNT` if bandwidth is underutilized
- Connection pool automatically scales with thread count
- GIL impact is minimal (I/O-bound workload)

## Legal and Compliance

**IMPORTANT**: This tool is for authorized bandwidth testing only. The code includes warnings for unlimited mode (lines 193-200).

When modifying:
- Maintain warning messages for unlimited traffic mode
- Do not remove or weaken legal disclaimers
- Consider adding rate limiting for public deployments

## Project Structure

```
.
├── bandwidth_tester.py      # Main application (single file)
├── Dockerfile               # Multi-stage Docker build
├── docker-compose.yml       # Production-ready orchestration
├── requirements.txt         # Python dependencies (requests==2.31.0)
├── README.md                # User documentation
├── DEPLOY.md                # Quick deployment guide
├── .dockerignore            # Docker build exclusions
└── .gitignore               # Git exclusions
```

## Versioning Strategy

- Use semantic versioning: `v1.0.1`, `v1.1.0`, etc.
- Always tag with both version and `latest`
- Update version in both Dockerfile ENV and git tags
- Document breaking changes in commit messages

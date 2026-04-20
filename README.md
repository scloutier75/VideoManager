# VideoManager

Full-stack application that scans local/NAS folders for video files, assesses their quality, and presents results in a searchable, sortable, filterable table.

**Stack:** FastAPI · PostgreSQL · Vue 3 · Element Plus

---

## Architecture

```
backend/
  app/
    api/          # FastAPI route handlers
    worker/
      analyzer.py # ffprobe metadata extraction + quality scoring (0–10)
      brisque.py  # Perceptual quality scoring via BRISQUE frame analysis
      scanner.py  # Recursive folder scanner
      scheduler.py# APScheduler periodic scan trigger
    config.py     # Pydantic settings (reads .env)
    crud.py       # Async DB queries
    database.py   # SQLAlchemy async engine + session
    models.py     # ORM models
    schemas.py    # Pydantic response schemas
    main.py       # FastAPI entry point
  backfill_brisque.py  # One-shot tool to populate brisque_score for existing rows
frontend/
  src/
    components/
      VideoTable.vue       # Main table with filters, sort, pagination
      VideoDetailDrawer.vue# Side drawer with full file details
      ScanPanel.vue        # Manual scan trigger
```

---

## Requirements

- Python 3.12+, Node 18+
- PostgreSQL (default: `localhost:5433`)
- `ffprobe` and `ffmpeg` in `$PATH`

---

## Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy and edit the environment file:

```bash
cp .env.example .env   # or edit .env directly
```

Key `.env` variables:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | `postgresql+asyncpg://user:pass@host:port/db` |
| `SCAN_FOLDERS` | — | Comma-separated absolute paths to scan |
| `SCAN_INTERVAL_MINUTES` | `60` | How often the background scan runs |
| `API_HOST` | `0.0.0.0` | Bind address |
| `API_PORT` | `9000` | Bind port |
| `ENABLE_BRISQUE` | `false` | Enable perceptual scoring during scans |
| `BRISQUE_FRAMES` | `5` | Frames sampled per video for BRISQUE |

Start the API:

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 9000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## Mounting a NAS (WSL)

```bash
sudo mkdir -p /mnt/v
sudo mount -t drvfs V: /mnt/v -o ro,uid=$(id -u),gid=$(id -g),metadata
```

Add the mount path to `SCAN_FOLDERS` in `.env`.

---

## Scoring

### Quality score (0–10)

Computed by `analyzer.py` using `ffprobe` metadata only — fast, no frame decoding.

| Component | Max points | Criteria |
|---|---|---|
| Resolution | 4 | 4K=4, 2K=3, 1080p=2, 720p=1 |
| Bitrate density | 3 | Bitrate relative to resolution |
| Codec | 2 | AV1=2, HEVC=2, H264=1, others=0 |
| Audio | 1 | Has audio stream |

### Efficiency score

`efficiency = quality_score × (reference_bitrate_for_resolution / actual_bitrate)`

Higher means better quality relative to file size. A score ≥ 8 is very efficient.

### BRISQUE score (0–10)

Computed by `brisque.py` using actual frame analysis — slower but catches visual artefacts (blur, noise, blocking, ringing) that metadata cannot.

Requires `ENABLE_BRISQUE=true` in `.env` for new scans, or run the backfill tool for existing files.

| Raw BRISQUE | Quality score | Interpretation |
|---|---|---|
| 0–10 | 9–10 | Nearly pristine |
| 10–40 | 6–9 | Good to very good |
| 40–70 | 3–6 | Noticeable issues |
| 70+ | 0–3 | Severely distorted |

---

## Backfill tool

`backend/backfill_brisque.py` populates `brisque_score` for rows that have `NULL` (i.e. files scanned before BRISQUE was enabled).

```bash
cd backend
source venv/bin/activate
python backfill_brisque.py [OPTIONS]
```

### Options

| Option | Default | Description |
|---|---|---|
| `--frames N` | `5` | Number of evenly-spaced frames to sample per video. More frames = more accurate but slower. |
| `--concurrency N` | `2` | Number of videos to process in parallel. Keep ≤ number of CPU cores. |
| `--dry-run` | off | Score files and log results, but do **not** write to the database. Useful for testing. |
| `--limit N` | none | Stop after processing N videos. Useful for a quick validation run. |

### Examples

```bash
# Full backfill with defaults (5 frames, 2 concurrent)
python backfill_brisque.py

# Higher accuracy, more parallelism
python backfill_brisque.py --frames 10 --concurrency 4

# Test on 3 files without touching the database
python backfill_brisque.py --limit 3 --dry-run

# Test that scoring works on a single file
python backfill_brisque.py --limit 1 --frames 3 --dry-run
```

### Notes

- Files already having a `brisque_score` value are always skipped.
- Files whose path no longer exists on disk are skipped with a warning.
- The script is safe to interrupt and re-run; already-scored rows are never re-processed.
- BRISQUE scoring requires `ffmpeg` and `opencv-python-headless` (included in `requirements.txt`).

---

## Kometizarr

Kometizarr adds visual overlays ("chips") onto Plex poster thumbnails — external ratings (TMDB,
IMDb, Rotten Tomatoes), your VideoManager quality score, and a 4K badge for UHD content.
The original poster is always backed up before the overlay is applied and can be restored at
any time from the UI.

**Location:** `kometizarr/kometizarr/`

### Prerequisites

- Docker and Docker Compose
- A running Plex server with an API token
- TMDB API key (free at <https://www.themoviedb.org/settings/api>)

### Quick start

```bash
cd kometizarr/kometizarr

# 1. Copy the example env and fill in your values
cp .env.example .env
$EDITOR .env

# 2. Start the stack
docker compose up -d

# 3. Open the UI
# http://localhost:3001
```

### Configuration (`.env`)

| Variable | Required | Description |
|---|---|---|
| `PLEX_URL` | ✅ | Plex server URL, e.g. `http://192.168.1.20:32400` |
| `PLEX_TOKEN` | ✅ | Plex authentication token ([how to find it](https://support.plex.tv/articles/204059436)) |
| `TMDB_API_KEY` | ✅ | TMDB API key for movie/show ratings |
| `OMDB_API_KEY` | optional | OMDb API key (supplements IMDb ratings) |
| `MDBLIST_API_KEY` | optional | MDBList key (adds Rotten Tomatoes critic & audience scores) |
| `VIDEOMANAGER_DB_URL` | optional | PostgreSQL DSN for VideoManager quality score integration — see below |

### Starting without Docker (development)

```bash
cd kometizarr/kometizarr

# Backend
pip install -r web/backend/requirements.txt
cd web/backend
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd web/frontend
npm install
npm run dev   # → http://localhost:5173
```

> **Note:** When running without Docker, set environment variables manually or create a `.env`
> file in `kometizarr/kometizarr/` and source it before starting the backend.

### Using the UI

1. **Select libraries** — tick the Plex libraries to process (Movies, TV Shows, etc.)
2. **Rating sources** — enable/disable individual badges:
   - 🎬 TMDB · ⭐ IMDb · 🍅 RT Critic · 🍿 RT Audience
   - 🎯 **VM Quality Score** — score from VideoManager (requires `VIDEOMANAGER_DB_URL`)
   - 📺 **4K Chip** — flat blue badge shown only on UHD (3840 × 2160) content
3. **Position badges** — drag each chip on the SVG poster preview; positions snap to grid
4. **Style** — adjust badge size, font, color and background opacity
5. Click **▶ Process** to apply overlays (backs up originals first)
6. Click **🔄 Restore** to remove overlays and return to original posters

### VideoManager quality score integration

Set `VIDEOMANAGER_DB_URL` in `.env` to the same PostgreSQL DSN used by VideoManager:

```
VIDEOMANAGER_DB_URL=postgresql://postgres:password@localhost:5433/video_manager
```

> If you copied the DSN from VideoManager's `.env`, remove the `+asyncpg` driver prefix —
> kometizarr uses `psycopg2`, not asyncpg.
> `postgresql+asyncpg://…` → `postgresql://…`

Once configured, enable the **🎯 VM Quality Score** checkbox in the UI. The backend looks up
each video's `score` column by exact file path (falls back to filename-only if the path differs
between Plex and VideoManager, e.g. different NAS mount points).

The badge colour is automatically adjusted to the same green / orange / red scale used in the
VideoManager table (green ≥ 8, orange ≥ 5, red < 5).

### 4K chip

Enable the **📺 4K Chip** checkbox. The backend reads the video resolution from Plex's media
metadata (`media[0].videoResolution`). The chip only appears if the resolution is `4k` or
`2160` — SD and 1080p files get no chip.

No external API or database is needed for this badge.

### Backups

Original posters are saved to `kometizarr/kometizarr/data/backups/` before any overlay is
applied. The directory structure is:

```
data/backups/
└── {Library}/
    └── {Title} ({Year})/
        ├── poster_original.jpg
        ├── poster_overlay.jpg
        └── metadata.json
```

**Do not delete this directory** — it is the only way to restore original Plex posters.


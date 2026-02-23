#!/usr/bin/env python3
"""
BlackRoad Video Transcoder - Video transcoding and format conversion pipeline
"""

import sqlite3
import uuid
import time
import math
import json
import os
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class OutputFormat(str, Enum):
    MP4 = "mp4"
    WEBM = "webm"
    HLS = "hls"
    DASH = "dash"


class VideoCodec(str, Enum):
    H264 = "h264"
    H265 = "h265"
    VP9 = "vp9"
    AV1 = "av1"


class Resolution(str, Enum):
    R360P = "360p"
    R480P = "480p"
    R720P = "720p"
    R1080P = "1080p"
    R4K = "4k"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


RESOLUTION_MAP: Dict[str, Tuple[int, int]] = {
    "360p": (640, 360),
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "4k": (3840, 2160),
}

CODEC_EFFICIENCY: Dict[str, float] = {
    "h264": 1.0,
    "h265": 0.6,
    "vp9": 0.65,
    "av1": 0.5,
}

FORMAT_OVERHEAD: Dict[str, float] = {
    "mp4": 1.02,
    "webm": 1.01,
    "hls": 1.08,
    "dash": 1.09,
}


@dataclass
class TranscodePreset:
    name: str
    codec: str
    resolution: str
    bitrate: int  # kbps
    fps: int
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TranscodeJob:
    id: str
    input_path: str
    output_path: str
    input_format: str
    output_format: str
    codec: str
    resolution: str
    bitrate_kbps: int
    fps: int
    status: str = JobStatus.PENDING.value
    progress: int = 0
    preset_name: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    input_size_bytes: int = 0
    output_size_bytes: int = 0
    duration_sec: float = 0.0
    segments: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["segments"] = json.dumps(self.segments)
        return d

    @property
    def width(self) -> int:
        return RESOLUTION_MAP.get(self.resolution, (1280, 720))[0]

    @property
    def height(self) -> int:
        return RESOLUTION_MAP.get(self.resolution, (1280, 720))[1]

    @property
    def elapsed_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        start = datetime.fromisoformat(self.started_at)
        end_str = self.completed_at or datetime.now(timezone.utc).isoformat()
        end = datetime.fromisoformat(end_str)
        return (end - start).total_seconds()


@dataclass
class HLSManifest:
    job_id: str
    base_url: str
    segments: List[str]
    target_duration: int = 6
    version: int = 3

    def render(self) -> str:
        lines = [
            "#EXTM3U",
            f"#EXT-X-VERSION:{self.version}",
            f"#EXT-X-TARGETDURATION:{self.target_duration}",
            "#EXT-X-MEDIA-SEQUENCE:0",
        ]
        for seg in self.segments:
            lines.append(f"#EXTINF:{self.target_duration}.000,")
            lines.append(f"{self.base_url}/{seg}")
        lines.append("#EXT-X-ENDLIST")
        return "\n".join(lines)


@dataclass
class DASHManifest:
    job_id: str
    base_url: str
    codec: str
    resolution: str
    bitrate_kbps: int
    duration_sec: float
    segments: List[str]
    segment_duration: int = 6

    def render(self) -> str:
        w, h = RESOLUTION_MAP.get(self.resolution, (1280, 720))
        total_ms = int(self.duration_sec * 1000)
        codec_map = {
            "h264": "avc1.64001f",
            "h265": "hvc1.1.6.L123.B0",
            "vp9": "vp09.00.10.08",
            "av1": "av01.0.04M.08",
        }
        codecs_str = codec_map.get(self.codec, "avc1.64001f")

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT{self.duration_sec:.3f}S">',
            '  <Period>',
            f'    <AdaptationSet mimeType="video/mp4" codecs="{codecs_str}" width="{w}" height="{h}">',
            f'      <Representation id="1" bandwidth="{self.bitrate_kbps * 1000}" width="{w}" height="{h}">',
            f'        <SegmentList timescale="1000" duration="{self.segment_duration * 1000}">',
        ]
        for seg in self.segments:
            lines.append(f'          <SegmentURL media="{self.base_url}/{seg}"/>')
        lines += [
            '        </SegmentList>',
            '      </Representation>',
            '    </AdaptationSet>',
            '  </Period>',
            '</MPD>',
        ]
        return "\n".join(lines)


class VideoTranscoder:
    """Main video transcoding pipeline manager."""

    DEFAULT_PRESETS = [
        TranscodePreset("web-hd", "h264", "720p", 2500, 30, "Web HD streaming"),
        TranscodePreset("web-sd", "h264", "480p", 1000, 30, "Web SD streaming"),
        TranscodePreset("mobile", "h264", "360p", 600, 24, "Mobile optimized"),
        TranscodePreset("4k-hdr", "h265", "4k", 15000, 60, "4K HDR premium"),
        TranscodePreset("web-vp9", "vp9", "720p", 2000, 30, "WebM/VP9 for Chrome"),
        TranscodePreset("av1-efficient", "av1", "1080p", 3000, 30, "AV1 efficient encode"),
    ]

    def __init__(self, db_path: str = "transcoder.db"):
        self.db_path = db_path
        self._init_db()
        self._seed_presets()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS transcode_jobs (
                    id TEXT PRIMARY KEY,
                    input_path TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    input_format TEXT NOT NULL,
                    output_format TEXT NOT NULL,
                    codec TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    bitrate_kbps INTEGER NOT NULL,
                    fps INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress INTEGER NOT NULL DEFAULT 0,
                    preset_name TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    input_size_bytes INTEGER DEFAULT 0,
                    output_size_bytes INTEGER DEFAULT 0,
                    duration_sec REAL DEFAULT 0.0,
                    segments TEXT DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS transcode_presets (
                    name TEXT PRIMARY KEY,
                    codec TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    bitrate INTEGER NOT NULL,
                    fps INTEGER NOT NULL,
                    description TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS batch_queues (
                    id TEXT PRIMARY KEY,
                    preset_name TEXT NOT NULL,
                    job_ids TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                );
            """)

    def _seed_presets(self):
        with self._connect() as conn:
            for preset in self.DEFAULT_PRESETS:
                conn.execute("""
                    INSERT OR IGNORE INTO transcode_presets
                    (name, codec, resolution, bitrate, fps, description, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (preset.name, preset.codec, preset.resolution,
                      preset.bitrate, preset.fps, preset.description, preset.created_at))

    def add_preset(self, name: str, config: dict) -> TranscodePreset:
        """Register a new transcoding preset."""
        preset = TranscodePreset(
            name=name,
            codec=config.get("codec", "h264"),
            resolution=config.get("resolution", "720p"),
            bitrate=config.get("bitrate", 2500),
            fps=config.get("fps", 30),
            description=config.get("description", ""),
        )
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO transcode_presets
                (name, codec, resolution, bitrate, fps, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (preset.name, preset.codec, preset.resolution,
                  preset.bitrate, preset.fps, preset.description, preset.created_at))
        return preset

    def get_preset(self, name: str) -> Optional[TranscodePreset]:
        """Retrieve a preset by name."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM transcode_presets WHERE name = ?", (name,)).fetchone()
        if not row:
            return None
        return TranscodePreset(**dict(row))

    def list_presets(self) -> List[TranscodePreset]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM transcode_presets ORDER BY name").fetchall()
        return [TranscodePreset(**dict(r)) for r in rows]

    def _detect_format(self, path: str) -> str:
        ext = Path(path).suffix.lower().lstrip(".")
        fmt_map = {
            "mp4": "mp4", "webm": "webm", "mkv": "mkv", "avi": "avi",
            "mov": "mov", "m3u8": "hls", "mpd": "dash", "ts": "ts",
        }
        return fmt_map.get(ext, "unknown")

    def _simulate_input_size(self, path: str) -> int:
        """Simulate file size based on path hash (no real file needed for demo)."""
        h = int(hashlib.md5(path.encode()).hexdigest(), 16)
        return (h % 900_000_000) + 100_000_000  # 100MB - 1GB

    def _simulate_duration(self, input_size_bytes: int, input_format: str) -> float:
        """Estimate duration from size (assume ~5Mbps average for input)."""
        avg_bitrate = 5_000_000  # bits/sec
        return (input_size_bytes * 8) / avg_bitrate

    def create_job(self, input_path: str, output_format: str,
                   preset: str, output_dir: str = "/tmp/transcoded") -> TranscodeJob:
        """Create a new transcode job."""
        preset_obj = self.get_preset(preset)
        if not preset_obj:
            raise ValueError(f"Preset '{preset}' not found")

        job_id = str(uuid.uuid4())
        ext_map = {"mp4": "mp4", "webm": "webm", "hls": "m3u8", "dash": "mpd"}
        ext = ext_map.get(output_format, output_format)
        output_path = f"{output_dir}/{job_id}.{ext}"
        input_size = self._simulate_input_size(input_path)

        job = TranscodeJob(
            id=job_id,
            input_path=input_path,
            output_path=output_path,
            input_format=self._detect_format(input_path),
            output_format=output_format,
            codec=preset_obj.codec,
            resolution=preset_obj.resolution,
            bitrate_kbps=preset_obj.bitrate,
            fps=preset_obj.fps,
            preset_name=preset,
            input_size_bytes=input_size,
        )
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO transcode_jobs
                (id, input_path, output_path, input_format, output_format, codec,
                 resolution, bitrate_kbps, fps, status, progress, preset_name,
                 created_at, input_size_bytes, duration_sec, segments)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (job.id, job.input_path, job.output_path, job.input_format,
                  job.output_format, job.codec, job.resolution, job.bitrate_kbps,
                  job.fps, job.status, job.progress, job.preset_name,
                  job.created_at, job.input_size_bytes, job.duration_sec, "[]"))
        return job

    def run_job(self, job_id: str) -> TranscodeJob:
        """Simulate running a transcode job with progress updates."""
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.status not in (JobStatus.PENDING.value, JobStatus.FAILED.value):
            raise ValueError(f"Job {job_id} is in status '{job.status}', cannot run")

        started = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("""
                UPDATE transcode_jobs SET status='running', started_at=?, progress=0
                WHERE id=?
            """, (started, job_id))

        # Simulate processing steps
        duration = self._simulate_duration(job.input_size_bytes, job.input_format)
        num_segments = max(1, int(duration / 6))
        segments = [f"seg_{i:04d}.ts" for i in range(num_segments)]

        output_size = self.estimate_output_size(job.input_path, job.preset_name or "web-hd")

        try:
            # Simulate encoding stages
            for progress in [10, 25, 50, 75, 90, 100]:
                with self._connect() as conn:
                    conn.execute("UPDATE transcode_jobs SET progress=? WHERE id=?",
                                 (progress, job_id))

            completed = datetime.now(timezone.utc).isoformat()
            with self._connect() as conn:
                conn.execute("""
                    UPDATE transcode_jobs
                    SET status='completed', progress=100, completed_at=?,
                        duration_sec=?, output_size_bytes=?, segments=?
                    WHERE id=?
                """, (completed, duration, output_size, json.dumps(segments), job_id))

        except Exception as e:
            with self._connect() as conn:
                conn.execute("""
                    UPDATE transcode_jobs SET status='failed', error_message=? WHERE id=?
                """, (str(e), job_id))

        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Optional[TranscodeJob]:
        """Retrieve a job by ID."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM transcode_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["segments"] = json.loads(d.get("segments") or "[]")
        return TranscodeJob(**d)

    def get_progress(self, job_id: str) -> dict:
        """Get job progress details."""
        job = self.get_job(job_id)
        if not job:
            return {"error": "Job not found"}
        return {
            "job_id": job.id,
            "status": job.status,
            "progress": job.progress,
            "elapsed_seconds": job.elapsed_seconds,
            "input_path": job.input_path,
            "output_format": job.output_format,
            "resolution": job.resolution,
        }

    def generate_hls_manifest(self, job_id: str, base_url: str = "https://cdn.blackroad.io/hls") -> str:
        """Generate an HLS .m3u8 manifest for a completed job."""
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.status != JobStatus.COMPLETED.value:
            raise ValueError(f"Job {job_id} not completed (status={job.status})")
        manifest = HLSManifest(
            job_id=job_id,
            base_url=f"{base_url}/{job_id}",
            segments=job.segments,
        )
        return manifest.render()

    def generate_dash_manifest(self, job_id: str, base_url: str = "https://cdn.blackroad.io/dash") -> str:
        """Generate a DASH .mpd manifest for a completed job."""
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.status != JobStatus.COMPLETED.value:
            raise ValueError(f"Job {job_id} not completed (status={job.status})")
        manifest = DASHManifest(
            job_id=job_id,
            base_url=f"{base_url}/{job_id}",
            codec=job.codec,
            resolution=job.resolution,
            bitrate_kbps=job.bitrate_kbps,
            duration_sec=job.duration_sec,
            segments=job.segments,
        )
        return manifest.render()

    def estimate_output_size(self, input_path: str, preset_name: str) -> int:
        """Estimate output file size in bytes."""
        preset = self.get_preset(preset_name)
        if not preset:
            return 0
        input_size = self._simulate_input_size(input_path)
        duration = self._simulate_duration(input_size, self._detect_format(input_path))
        codec_eff = CODEC_EFFICIENCY.get(preset.codec, 1.0)
        fmt_overhead = FORMAT_OVERHEAD.get("mp4", 1.02)
        # bits = bitrate_kbps * 1000 * duration, then bytes
        video_bytes = int((preset.bitrate * 1000 * duration) / 8)
        audio_bytes = int((128 * 1000 * duration) / 8)  # 128kbps audio
        return int((video_bytes + audio_bytes) * codec_eff * fmt_overhead)

    def queue_batch(self, files: List[str], preset: str,
                    output_format: str = "mp4") -> dict:
        """Queue multiple files for transcoding."""
        batch_id = str(uuid.uuid4())
        job_ids = []
        for f in files:
            job = self.create_job(f, output_format, preset)
            job_ids.append(job.id)

        with self._connect() as conn:
            conn.execute("""
                INSERT INTO batch_queues (id, preset_name, job_ids, created_at, status)
                VALUES (?, ?, ?, ?, 'pending')
            """, (batch_id, preset, json.dumps(job_ids),
                  datetime.now(timezone.utc).isoformat()))

        return {
            "batch_id": batch_id,
            "preset": preset,
            "total_jobs": len(job_ids),
            "job_ids": job_ids,
        }

    def run_batch(self, batch_id: str) -> dict:
        """Run all jobs in a batch."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM batch_queues WHERE id=?", (batch_id,)).fetchone()
        if not row:
            raise ValueError(f"Batch {batch_id} not found")

        job_ids = json.loads(row["job_ids"])
        results = {"completed": [], "failed": []}

        with self._connect() as conn:
            conn.execute("UPDATE batch_queues SET status='running' WHERE id=?", (batch_id,))

        for jid in job_ids:
            try:
                job = self.run_job(jid)
                if job.status == JobStatus.COMPLETED.value:
                    results["completed"].append(jid)
                else:
                    results["failed"].append(jid)
            except Exception:
                results["failed"].append(jid)

        final_status = "completed" if not results["failed"] else "partial"
        with self._connect() as conn:
            conn.execute("UPDATE batch_queues SET status=? WHERE id=?", (final_status, batch_id))

        return results

    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> List[TranscodeJob]:
        """List jobs, optionally filtered by status."""
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM transcode_jobs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                    (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM transcode_jobs ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
        jobs = []
        for row in rows:
            d = dict(row)
            d["segments"] = json.loads(d.get("segments") or "[]")
            jobs.append(TranscodeJob(**d))
        return jobs

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job."""
        with self._connect() as conn:
            result = conn.execute("""
                UPDATE transcode_jobs SET status='cancelled'
                WHERE id=? AND status='pending'
            """, (job_id,))
        return result.rowcount > 0

    def get_stats(self) -> dict:
        """Get overall transcoder statistics."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM transcode_jobs").fetchone()[0]
            by_status = conn.execute("""
                SELECT status, COUNT(*) as cnt FROM transcode_jobs GROUP BY status
            """).fetchall()
            avg_output = conn.execute("""
                SELECT AVG(output_size_bytes) FROM transcode_jobs WHERE status='completed'
            """).fetchone()[0]
            total_output_gb = conn.execute("""
                SELECT SUM(output_size_bytes) / 1073741824.0 FROM transcode_jobs WHERE status='completed'
            """).fetchone()[0]

        return {
            "total_jobs": total,
            "by_status": {r["status"]: r["cnt"] for r in by_status},
            "avg_output_bytes": int(avg_output or 0),
            "total_output_gb": round(total_output_gb or 0, 3),
        }


def _parse_resolution(res_str: str) -> Tuple[int, int]:
    """Parse resolution string to (width, height)."""
    return RESOLUTION_MAP.get(res_str, (1280, 720))


def _calculate_bitrate_for_resolution(resolution: str, codec: str) -> int:
    """Calculate recommended bitrate for a resolution/codec combo."""
    base_bitrates = {"360p": 800, "480p": 1500, "720p": 3000, "1080p": 6000, "4k": 20000}
    base = base_bitrates.get(resolution, 3000)
    efficiency = CODEC_EFFICIENCY.get(codec, 1.0)
    return int(base * efficiency)


def create_transcoder(db_path: str = "transcoder.db") -> VideoTranscoder:
    """Factory function to create a VideoTranscoder instance."""
    return VideoTranscoder(db_path=db_path)


if __name__ == "__main__":
    import sys

    transcoder = create_transcoder()

    print("BlackRoad Video Transcoder")
    print("=" * 40)
    print(f"Available presets: {[p.name for p in transcoder.list_presets()]}")

    # Demo: create and run a job
    job = transcoder.create_job(
        input_path="/media/input/sample_video.mkv",
        output_format="hls",
        preset="web-hd",
    )
    print(f"\nCreated job: {job.id}")
    print(f"Input: {job.input_path}")
    print(f"Output format: {job.output_format}")
    print(f"Resolution: {job.resolution} ({job.width}x{job.height})")
    print(f"Codec: {job.codec}")

    completed = transcoder.run_job(job.id)
    print(f"\nJob completed: {completed.status}")
    print(f"Duration: {completed.duration_sec:.1f}s")
    print(f"Output size: {completed.output_size_bytes / 1024 / 1024:.1f}MB")
    print(f"Segments: {len(completed.segments)}")

    hls = transcoder.generate_hls_manifest(job.id)
    print(f"\nHLS Manifest (first 200 chars):\n{hls[:200]}...")

    estimated = transcoder.estimate_output_size("/media/test.mp4", "web-hd")
    print(f"\nEstimated output size for web-hd: {estimated / 1024 / 1024:.1f}MB")

    batch = transcoder.queue_batch(
        ["/media/vid1.mp4", "/media/vid2.mp4", "/media/vid3.mp4"],
        preset="mobile",
    )
    print(f"\nQueued batch: {batch['batch_id']}")
    print(f"Total jobs: {batch['total_jobs']}")

    stats = transcoder.get_stats()
    print(f"\nStats: {stats}")

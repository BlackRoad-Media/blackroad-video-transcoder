# BlackRoad Video Transcoder

> Video transcoding and format conversion pipeline — part of the BlackRoad Media suite.

[![CI](https://github.com/BlackRoad-Media/blackroad-video-transcoder/actions/workflows/ci.yml/badge.svg)](https://github.com/BlackRoad-Media/blackroad-video-transcoder/actions/workflows/ci.yml)

## Features

- **Multi-format output**: MP4, WebM, HLS (adaptive streaming), DASH
- **Codec support**: H.264, H.265/HEVC, VP9, AV1
- **Resolutions**: 360p → 4K
- **Preset system**: Built-in and custom presets
- **Batch transcoding**: Queue multiple files
- **Manifest generation**: HLS `.m3u8` and DASH `.mpd`
- **Size estimation**: Pre-flight output size calculation
- **SQLite persistence**: All jobs and presets stored

## Quick Start

```bash
pip install -r requirements.txt
python video_transcoder.py
```

## Usage

```python
from video_transcoder import create_transcoder

t = create_transcoder()

# Create and run a job
job = t.create_job("/path/to/video.mkv", output_format="hls", preset="web-hd")
completed = t.run_job(job.id)

# Generate HLS manifest
manifest = t.generate_hls_manifest(job.id)

# Batch transcode
batch = t.queue_batch(["/vid1.mp4", "/vid2.mp4"], preset="mobile")
results = t.run_batch(batch["batch_id"])
```

## Presets

| Preset | Codec | Resolution | Bitrate |
|--------|-------|------------|---------|
| web-hd | H.264 | 720p | 2500 kbps |
| web-sd | H.264 | 480p | 1000 kbps |
| mobile | H.264 | 360p | 600 kbps |
| 4k-hdr | H.265 | 4K | 15000 kbps |
| web-vp9 | VP9 | 720p | 2000 kbps |
| av1-efficient | AV1 | 1080p | 3000 kbps |

## Testing

```bash
pytest tests/ -v --cov=video_transcoder
```

## License

Proprietary — © BlackRoad OS, Inc.

<!-- BlackRoad SEO Enhanced -->

# ulackroad video transcoder

> Part of **[BlackRoad OS](https://blackroad.io)** — Sovereign Computing for Everyone

[![BlackRoad OS](https://img.shields.io/badge/BlackRoad-OS-ff1d6c?style=for-the-badge)](https://blackroad.io)
[![BlackRoad Media](https://img.shields.io/badge/Org-BlackRoad-Media-2979ff?style=for-the-badge)](https://github.com/BlackRoad-Media)
[![License](https://img.shields.io/badge/License-Proprietary-f5a623?style=for-the-badge)](LICENSE)

**ulackroad video transcoder** is part of the **BlackRoad OS** ecosystem — a sovereign, distributed operating system built on edge computing, local AI, and mesh networking by **BlackRoad OS, Inc.**

## About BlackRoad OS

BlackRoad OS is a sovereign computing platform that runs AI locally on your own hardware. No cloud dependencies. No API keys. No surveillance. Built by [BlackRoad OS, Inc.](https://github.com/BlackRoad-OS-Inc), a Delaware C-Corp founded in 2025.

### Key Features
- **Local AI** — Run LLMs on Raspberry Pi, Hailo-8, and commodity hardware
- **Mesh Networking** — WireGuard VPN, NATS pub/sub, peer-to-peer communication
- **Edge Computing** — 52 TOPS of AI acceleration across a Pi fleet
- **Self-Hosted Everything** — Git, DNS, storage, CI/CD, chat — all sovereign
- **Zero Cloud Dependencies** — Your data stays on your hardware

### The BlackRoad Ecosystem
| Organization | Focus |
|---|---|
| [BlackRoad OS](https://github.com/BlackRoad-OS) | Core platform and applications |
| [BlackRoad OS, Inc.](https://github.com/BlackRoad-OS-Inc) | Corporate and enterprise |
| [BlackRoad AI](https://github.com/BlackRoad-AI) | Artificial intelligence and ML |
| [BlackRoad Hardware](https://github.com/BlackRoad-Hardware) | Edge hardware and IoT |
| [BlackRoad Security](https://github.com/BlackRoad-Security) | Cybersecurity and auditing |
| [BlackRoad Quantum](https://github.com/BlackRoad-Quantum) | Quantum computing research |
| [BlackRoad Agents](https://github.com/BlackRoad-Agents) | Autonomous AI agents |
| [BlackRoad Network](https://github.com/BlackRoad-Network) | Mesh and distributed networking |
| [BlackRoad Education](https://github.com/BlackRoad-Education) | Learning and tutoring platforms |
| [BlackRoad Labs](https://github.com/BlackRoad-Labs) | Research and experiments |
| [BlackRoad Cloud](https://github.com/BlackRoad-Cloud) | Self-hosted cloud infrastructure |
| [BlackRoad Forge](https://github.com/BlackRoad-Forge) | Developer tools and utilities |

### Links
- **Website**: [blackroad.io](https://blackroad.io)
- **Documentation**: [docs.blackroad.io](https://docs.blackroad.io)
- **Chat**: [chat.blackroad.io](https://chat.blackroad.io)
- **Search**: [search.blackroad.io](https://search.blackroad.io)

---


> Video transcoding and format conversion pipeline

Part of the [BlackRoad OS](https://blackroad.io) ecosystem — [BlackRoad-Media](https://github.com/BlackRoad-Media)

---

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

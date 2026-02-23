import pytest
import os
import tempfile
from video_transcoder import (
    VideoTranscoder, TranscodeJob, TranscodePreset, HLSManifest, DASHManifest,
    JobStatus, OutputFormat, VideoCodec, Resolution,
    _parse_resolution, _calculate_bitrate_for_resolution, create_transcoder,
    RESOLUTION_MAP, CODEC_EFFICIENCY,
)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_transcoder.db")


@pytest.fixture
def transcoder(db_path):
    return VideoTranscoder(db_path=db_path)


class TestPresets:
    def test_default_presets_loaded(self, transcoder):
        presets = transcoder.list_presets()
        assert len(presets) >= 6

    def test_get_preset(self, transcoder):
        p = transcoder.get_preset("web-hd")
        assert p is not None
        assert p.codec == "h264"
        assert p.resolution == "720p"

    def test_add_custom_preset(self, transcoder):
        p = transcoder.add_preset("custom-4k", {
            "codec": "h265", "resolution": "4k", "bitrate": 20000, "fps": 60
        })
        assert p.name == "custom-4k"
        fetched = transcoder.get_preset("custom-4k")
        assert fetched is not None
        assert fetched.codec == "h265"

    def test_get_nonexistent_preset(self, transcoder):
        assert transcoder.get_preset("nonexistent") is None


class TestJobCreation:
    def test_create_job_returns_job(self, transcoder):
        job = transcoder.create_job("/input/video.mkv", "mp4", "web-hd")
        assert job.id is not None
        assert job.status == JobStatus.PENDING.value
        assert job.output_format == "mp4"
        assert job.codec == "h264"

    def test_create_job_invalid_preset(self, transcoder):
        with pytest.raises(ValueError, match="not found"):
            transcoder.create_job("/input/video.mkv", "mp4", "nonexistent-preset")

    def test_create_job_hls_format(self, transcoder):
        job = transcoder.create_job("/input/video.mp4", "hls", "web-hd")
        assert job.output_path.endswith(".m3u8")

    def test_create_job_dash_format(self, transcoder):
        job = transcoder.create_job("/input/video.mp4", "dash", "web-hd")
        assert job.output_path.endswith(".mpd")

    def test_job_stored_in_db(self, transcoder):
        job = transcoder.create_job("/input/video.mkv", "mp4", "mobile")
        fetched = transcoder.get_job(job.id)
        assert fetched is not None
        assert fetched.id == job.id


class TestJobExecution:
    def test_run_job_completes(self, transcoder):
        job = transcoder.create_job("/input/video.mkv", "mp4", "web-hd")
        completed = transcoder.run_job(job.id)
        assert completed.status == JobStatus.COMPLETED.value
        assert completed.progress == 100
        assert completed.duration_sec > 0

    def test_run_job_sets_segments(self, transcoder):
        job = transcoder.create_job("/input/video.mkv", "hls", "web-hd")
        completed = transcoder.run_job(job.id)
        assert len(completed.segments) > 0

    def test_run_nonexistent_job(self, transcoder):
        with pytest.raises(ValueError):
            transcoder.run_job("nonexistent-id")

    def test_run_completed_job_raises(self, transcoder):
        job = transcoder.create_job("/input/video.mkv", "mp4", "web-sd")
        transcoder.run_job(job.id)
        with pytest.raises(ValueError, match="completed"):
            transcoder.run_job(job.id)

    def test_get_progress(self, transcoder):
        job = transcoder.create_job("/input/video.mkv", "mp4", "web-hd")
        prog = transcoder.get_progress(job.id)
        assert prog["job_id"] == job.id
        assert prog["status"] == "pending"

    def test_cancel_pending_job(self, transcoder):
        job = transcoder.create_job("/input/video.mkv", "mp4", "web-hd")
        result = transcoder.cancel_job(job.id)
        assert result is True
        fetched = transcoder.get_job(job.id)
        assert fetched.status == JobStatus.CANCELLED.value


class TestManifests:
    def test_generate_hls_manifest(self, transcoder):
        job = transcoder.create_job("/input/video.mkv", "hls", "web-hd")
        transcoder.run_job(job.id)
        manifest = transcoder.generate_hls_manifest(job.id)
        assert "#EXTM3U" in manifest
        assert "#EXT-X-ENDLIST" in manifest

    def test_generate_dash_manifest(self, transcoder):
        job = transcoder.create_job("/input/video.mkv", "dash", "web-hd")
        transcoder.run_job(job.id)
        manifest = transcoder.generate_dash_manifest(job.id)
        assert '<?xml' in manifest
        assert 'MPD' in manifest

    def test_hls_manifest_pending_raises(self, transcoder):
        job = transcoder.create_job("/input/video.mkv", "mp4", "web-hd")
        with pytest.raises(ValueError):
            transcoder.generate_hls_manifest(job.id)


class TestBatchAndEstimation:
    def test_queue_batch(self, transcoder):
        files = ["/input/a.mp4", "/input/b.mp4"]
        batch = transcoder.queue_batch(files, "mobile")
        assert batch["total_jobs"] == 2
        assert len(batch["job_ids"]) == 2

    def test_estimate_output_size(self, transcoder):
        size = transcoder.estimate_output_size("/input/video.mp4", "web-hd")
        assert size > 0

    def test_get_stats(self, transcoder):
        transcoder.create_job("/input/video.mkv", "mp4", "web-hd")
        stats = transcoder.get_stats()
        assert "total_jobs" in stats
        assert stats["total_jobs"] >= 1

    def test_list_jobs(self, transcoder):
        transcoder.create_job("/input/video.mkv", "mp4", "web-hd")
        jobs = transcoder.list_jobs()
        assert len(jobs) >= 1

    def test_resolution_map_values(self):
        for res, (w, h) in RESOLUTION_MAP.items():
            assert w > 0 and h > 0

    def test_parse_resolution(self):
        w, h = _parse_resolution("720p")
        assert w == 1280 and h == 720

    def test_calculate_bitrate(self):
        bitrate = _calculate_bitrate_for_resolution("1080p", "h265")
        assert bitrate > 0

    def test_create_transcoder_factory(self, tmp_path):
        t = create_transcoder(str(tmp_path / "factory.db"))
        assert t is not None
        assert len(t.list_presets()) > 0

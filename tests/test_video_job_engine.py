from pathlib import Path
from tui_transcript.models import VideoJob


def test_video_job_default_engine_is_deepgram():
    job = VideoJob(path=Path("/tmp/x.mp4"))
    assert job.engine == "deepgram"
    assert job.whisper_model is None


def test_video_job_engine_serializes():
    job = VideoJob(
        path=Path("/tmp/x.mp4"),
        engine="whisper_local",
        whisper_model="large-v3",
    )
    d = job.to_dict()
    assert d["engine"] == "whisper_local"
    assert d["whisper_model"] == "large-v3"


def test_video_job_engine_round_trip():
    job = VideoJob(
        path=Path("/tmp/x.mp4"),
        engine="whisper_local",
        whisper_model="medium",
    )
    restored = VideoJob.from_dict(job.to_dict())
    assert restored.engine == "whisper_local"
    assert restored.whisper_model == "medium"


def test_video_job_engine_defaults_when_missing_in_dict():
    restored = VideoJob.from_dict({"path": "/tmp/x.mp4"})
    assert restored.engine == "deepgram"
    assert restored.whisper_model is None

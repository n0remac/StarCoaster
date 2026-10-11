"""Focused tests for the optional graphical recorder."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import video_capture as video


class VideoConfigTests(unittest.TestCase):
    def test_combined_command(self):
        config = video.VideoConfig()
        command = video.command_for(config, Path("combined.mp4"))
        self.assertEqual(config.resolution, (1920, 600))
        self.assertEqual(command.count("-i"), 2)
        self.assertIn(":91.0", command)
        self.assertIn(":92.0", command)
        self.assertIn("[a][b]hstack=inputs=2[v]", command[command.index("-filter_complex") + 1])
        self.assertEqual(command[-1], "combined.mp4")
        self.assertEqual(command[command.index("-pix_fmt") + 1], "yuv420p")

    def test_separate_commands(self):
        config = video.VideoConfig(layout="separate", width=640, fps=5, preset="ultrafast")
        self.assertEqual(config.resolution, (640, 400))
        a = video.command_for(config, Path("client-a.mp4"), "client-a")
        b = video.command_for(config, Path("client-b.mp4"), "client-b")
        self.assertEqual(a.count("-i"), 1)
        self.assertIn(":91.0", a)
        self.assertNotIn(":92.0", a)
        self.assertIn(":92.0", b)
        self.assertEqual(a[a.index("-vf") + 1], "scale=640:400:flags=fast_bilinear")

    def test_even_aspect_ratio_and_invalid_values(self):
        self.assertEqual(video.VideoConfig(width=962).resolution, (1924, 602))
        for kwargs in ({"fps": 0}, {"fps": 61}, {"width": 0}, {"width": 961},
                       {"width": 1282}, {"crf": 52}, {"preset": "invalid"},
                       {"layout": "both"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                video.VideoConfig(**kwargs)

    def test_missing_binaries(self):
        with patch.object(video.shutil, "which", side_effect=lambda name: None if name == "ffprobe" else "/usr/bin/ffmpeg"):
            with self.assertRaisesRegex(RuntimeError, "ffprobe"):
                video.check_dependencies()

    def test_missing_h264_encoder(self):
        with patch.object(video.shutil, "which", return_value="/usr/bin/tool"), \
             patch.object(video.subprocess, "run", return_value=Mock(returncode=0, stdout="no H.264 encoder")):
            with self.assertRaisesRegex(RuntimeError, "libx264"):
                video.check_dependencies()

    def test_ffprobe_checks_codec_resolution_and_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "combined.mp4"
            path.write_bytes(b"test video")
            good = {"streams": [{"codec_name": "h264", "width": 1920, "height": 600,
                                  "nb_read_frames": "100", "avg_frame_rate": "10/1"}],
                    "format": {"duration": "10.0"}}
            with patch.object(video.subprocess, "run", return_value=Mock(stdout=json.dumps(good))):
                self.assertEqual(video.probe_video(path, (1920, 600))["measured_fps"], 10)
                with self.assertRaisesRegex(RuntimeError, "resolution"):
                    video.probe_video(path, (960, 600))
            good["streams"][0]["nb_read_frames"] = "0"
            with patch.object(video.subprocess, "run", return_value=Mock(stdout=json.dumps(good))):
                with self.assertRaisesRegex(RuntimeError, "empty"):
                    video.probe_video(path, (1920, 600))


class RecorderTests(unittest.TestCase):
    def test_start_stop_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Mock()
            process.poll.return_value = None
            process.wait.return_value = 0
            with patch.object(video.subprocess, "Popen", return_value=process), \
                 patch.object(video, "probe_video", return_value={"filename": "combined.mp4", "measured_fps": 9.9, "duration_seconds": 0.1}):
                recorder = video.VideoRecorder(video.VideoConfig(), Path(directory))
                recorder.start()
                recorder.event("screenshot", filename="client-a-t2.png")
                result = recorder.stop(True)
            process.send_signal.assert_called_once_with(video.signal.SIGINT)
            self.assertEqual(result["test_status"], "passed")
            self.assertEqual(result["events"][0]["event"], "screenshot")
            self.assertIn("seconds_from_recording_start", result["events"][0])
            self.assertIn("video_start_offset_seconds_estimate", result["outputs"][0])
            self.assertEqual(json.loads((Path(directory) / "video-metadata.json").read_text())["outputs"], result["outputs"])

    def test_forced_cleanup_reports_failure_and_retains_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Mock()
            process.poll.return_value = None
            process.wait.side_effect = [video.subprocess.TimeoutExpired("ffmpeg", 10), -9]
            with patch.object(video.subprocess, "Popen", return_value=process), \
                 patch.object(video, "probe_video", side_effect=RuntimeError("invalid MP4")):
                recorder = video.VideoRecorder(video.VideoConfig(), Path(directory))
                recorder.start()
                with self.assertRaisesRegex(RuntimeError, "forced termination"):
                    recorder.stop(False, "test failed")
            process.kill.assert_called_once()
            result = json.loads((Path(directory) / "video-metadata.json").read_text())
            self.assertEqual(result["test_status"], "failed")
            self.assertEqual(result["test_error"], "test failed")
            self.assertTrue(result["recording_errors"])

    def test_ffmpeg_sigint_status_255_is_valid_after_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Mock()
            process.poll.return_value = None
            process.wait.return_value = 255
            with patch.object(video.subprocess, "Popen", return_value=process), \
                 patch.object(video, "probe_video", return_value={"filename": "combined.mp4", "duration_seconds": 0.1}):
                recorder = video.VideoRecorder(video.VideoConfig(), Path(directory))
                recorder.start()
                result = recorder.stop(True)
            self.assertEqual(result["test_status"], "passed")
            self.assertEqual(result["recording_errors"], [])

    def test_separate_start_failure_stops_first_encoder(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Mock()
            first.poll.return_value = None
            first.wait.return_value = 255
            with patch.object(video.subprocess, "Popen",
                              side_effect=[first, OSError("second encoder failed")]):
                recorder = video.VideoRecorder(video.VideoConfig(layout="separate"), Path(directory))
                with self.assertRaisesRegex(OSError, "second encoder failed"):
                    recorder.start()
            first.send_signal.assert_called_once_with(video.signal.SIGINT)
            self.assertIsNone(recorder.log)

    def test_test_failure_retains_valid_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Mock()
            process.poll.return_value = None
            process.wait.return_value = 255
            with patch.object(video.subprocess, "Popen", return_value=process), \
                 patch.object(video, "probe_video", return_value={"filename": "combined.mp4", "measured_fps": 10, "duration_seconds": 0.1}):
                recorder = video.VideoRecorder(video.VideoConfig(), Path(directory))
                recorder.start()
                result = recorder.stop(False, "sprite verification failed")
            self.assertEqual(result["test_status"], "failed")
            self.assertEqual(result["outputs"][0]["filename"], "combined.mp4")
            self.assertEqual(result["recording_errors"], [])

    def test_early_exit_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Mock()
            process.poll.side_effect = [None, 1, 1]
            process.wait.return_value = 1
            with patch.object(video.subprocess, "Popen", return_value=process):
                recorder = video.VideoRecorder(video.VideoConfig(), Path(directory))
                recorder.start()
                with self.assertRaisesRegex(RuntimeError, "exited early"):
                    recorder.check_alive()
                with patch.object(video, "probe_video", side_effect=RuntimeError("truncated")):
                    with self.assertRaisesRegex(RuntimeError, "video recording failed"):
                        recorder.stop(False, "FFmpeg exited early")


class ExistingWorkflowTests(unittest.TestCase):
    def test_disabled_recording_does_not_check_ffmpeg(self):
        spec = importlib.util.spec_from_file_location("capture_live_demo", SCRIPTS / "capture-live-demo.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rct2/Data").mkdir(parents=True)
            (root / "rct2/Data/g1.dat").touch()
            (root / "starcraft").mkdir()
            for name in ("StarDat.mpq", "BrooDat.mpq", "Patch_rt.mpq"):
                (root / "starcraft" / name).touch()
            with patch.object(module, "RCT2_DATA", root / "rct2"), \
                 patch.object(module, "SC_DATA", root / "starcraft"), \
                 patch.object(module, "OUT", root / "out"), \
             patch("artifact_runs.ARTIFACT_ROOT", root / "artifacts"), \
                 patch.object(module, "start", side_effect=RuntimeError("stopped before launch")), \
                 patch.object(module, "check_dependencies") as dependencies, \
                 patch.object(sys, "argv", ["capture-live-demo.py", "--seconds", "8", "--video-fps", "0"]):
                with self.assertRaisesRegex(RuntimeError, "stopped before launch"):
                    module.main()
            dependencies.assert_not_called()


if __name__ == "__main__":
    unittest.main()

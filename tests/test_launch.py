"""Regression tests for launch-time engine selection."""
# SPDX-License-Identifier: MIT

import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from bol import launch


class GraphicsEngineLaunchTests(unittest.TestCase):
    def _exercise_ready_launch(self, root, popen, arm, disarm,
                               prefix_idle=True):
        content = root / "content"
        logs = root / "logs"
        data = root / "data"
        content.mkdir()
        logs.mkdir()
        data.mkdir()
        (content / "Minecraft.Windows.exe").write_bytes(b"MZ")
        settings = {"game_dir": str(content)}
        patches = (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(launch, "CONTENT", content),
            mock.patch.object(launch, "LOGS", logs),
            mock.patch.object(launch, "DATA", data),
            mock.patch.object(launch, "load_settings", return_value=settings),
            mock.patch.object(launch, "proton_path",
                              return_value=Path("/tmp/fake-engine")),
            mock.patch.object(launch, "require_safe_graphics_session"),
            mock.patch.object(launch, "_prepare_launch_engine"),
            mock.patch.object(
                launch, "msa_session_snapshot",
                return_value=({"refresh_token": "refresh"}, "a" * 32)),
            mock.patch.object(launch, "msa_refresh", return_value=None),
            mock.patch.object(launch, "msa_save_for_account_epoch",
                              return_value=True),
            mock.patch.object(launch, "account_epoch_is_current",
                              return_value=True),
            mock.patch.object(launch, "boot_prefix", return_value=True),
            mock.patch.object(launch, "wine_apply_winegdk_prereqs"),
            mock.patch.object(launch, "_install_cryptbase_in_prefix"),
            mock.patch.object(launch, "install_gameinput"),
            mock.patch.object(launch, "wine_reg_set_refresh_token",
                              return_value=True),
            mock.patch.object(launch, "ensure_login_deps"),
            mock.patch.object(launch, "xbl_preauth", return_value=True),
            mock.patch.object(launch, "bump_stack_reserve"),
            mock.patch.object(launch, "proton_umu_cmd",
                              return_value=(["fake-umu"], {})),
            mock.patch.object(launch, "patch_options"),
            mock.patch.object(launch, "diagnose", return_value=[]),
            mock.patch.object(launch, "_prefix_stably_idle_after_wrapper",
                              return_value=prefix_idle),
            mock.patch.object(launch, "arm_gpu_launch", side_effect=arm),
            mock.patch.object(launch, "disarm_gpu_launch", side_effect=disarm),
            mock.patch.object(launch.subprocess, "Popen", side_effect=popen),
            mock.patch.object(launch, "info"),
            mock.patch.object(launch, "ok"),
            mock.patch.object(launch, "warn"),
        )
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            return launch._launch_once()

    def test_managed_install_finishes_before_graphics_validation(self):
        calls = []
        with mock.patch.object(launch, "active_prefix",
                               return_value=Path("/tmp/bol-prefix")), \
                mock.patch.object(
                    launch, "prefix_processes",
                    side_effect=lambda _prefix: calls.append("idle") or []), \
                mock.patch.object(launch, "custom_proton", return_value=False), \
                mock.patch.object(launch, "ensure_winegdk",
                                  side_effect=lambda: calls.append("install")), \
                mock.patch.object(launch, "_prepare_graphics_engine",
                                  side_effect=lambda: calls.append("graphics")):
            launch._prepare_launch_engine()
        self.assertEqual(calls, ["idle", "install", "graphics"])

    def test_rejected_managed_install_never_reaches_graphics_or_wine(self):
        with mock.patch.object(launch, "active_prefix",
                               return_value=Path("/tmp/bol-prefix")), \
                mock.patch.object(launch, "prefix_processes",
                                  return_value=[]) as processes, \
                mock.patch.object(launch, "custom_proton", return_value=False), \
                mock.patch.object(launch, "ensure_winegdk",
                                  side_effect=launch.BolError("stale r10")), \
                mock.patch.object(launch, "_prepare_graphics_engine") as graphics, \
                mock.patch.object(launch, "patch_proton") as patch:
            with self.assertRaisesRegex(launch.BolError, "stale r10"):
                launch._prepare_launch_engine()
        processes.assert_called_once_with(Path("/tmp/bol-prefix"))
        graphics.assert_not_called()
        patch.assert_not_called()

    def test_running_prefix_is_refused_not_killed(self):
        with mock.patch.object(launch, "active_prefix",
                               return_value=Path("/tmp/bol-prefix")), \
                mock.patch.object(launch, "prefix_processes",
                                  return_value=[12, 34]), \
                mock.patch.object(launch, "ensure_winegdk") as install:
            with self.assertRaisesRegex(launch.BolError, "already active"):
                launch._prepare_launch_engine()
        install.assert_not_called()

    def test_managed_engine_activates_compatible_variant(self):
        engine = Path("/tmp/GDK-Proton-xuser")
        with mock.patch.object(launch, "custom_proton", return_value=False), \
                mock.patch.object(launch, "proton_path", return_value=engine), \
                mock.patch.object(launch, "prepare_universal_vkd3d",
                                  return_value=("nv-dgc", True)) as prepare, \
                mock.patch.object(launch, "info"):
            self.assertEqual(launch._prepare_graphics_engine(), "nv-dgc")
        prepare.assert_called_once_with(engine, launch.WINEGDK_BUILD_REV)

    def test_user_supplied_engine_is_never_rewritten(self):
        with mock.patch.object(launch, "custom_proton", return_value=True), \
                mock.patch.object(launch, "prepare_universal_vkd3d") as prepare:
            self.assertIsNone(launch._prepare_graphics_engine())
        prepare.assert_not_called()

    def test_managed_engine_validation_error_is_visible(self):
        with mock.patch.object(launch, "custom_proton", return_value=False), \
                mock.patch.object(launch, "proton_path",
                                  return_value=Path("/tmp/engine")), \
                mock.patch.object(launch, "prepare_universal_vkd3d",
                                  side_effect=launch.BolError(
                                      "engine revision mismatch")), \
                mock.patch.object(launch, "die",
                                  side_effect=launch.BolError) as die:
            with self.assertRaises(launch.BolError):
                launch._prepare_graphics_engine()
        die.assert_called_once_with("engine revision mismatch")

    def test_raw_va_workaround_preserves_user_vkd3d_options(self):
        env = {"VKD3D_CONFIG": "breadcrumbs;single_queue"}
        launch._require_vkd3d_config(env, "force_raw_va_cbv")
        self.assertEqual(
            env["VKD3D_CONFIG"],
            "breadcrumbs,single_queue,force_raw_va_cbv",
        )

    def test_raw_va_workaround_is_idempotent(self):
        env = {"VKD3D_CONFIG": "force_raw_va_cbv,breadcrumbs"}
        launch._require_vkd3d_config(env, "force_raw_va_cbv")
        self.assertEqual(env["VKD3D_CONFIG"],
                         "force_raw_va_cbv,breadcrumbs")

    def test_gpu_safety_failure_happens_before_engine_or_wine(self):
        with tempfile.TemporaryDirectory() as td:
            game = Path(td)
            (game / "Minecraft.Windows.exe").write_bytes(b"MZ")
            with mock.patch.object(launch, "load_settings",
                                   return_value={"game_dir": str(game)}), \
                    mock.patch.object(launch, "proton_path",
                                      return_value=Path("/tmp/engine")), \
                    mock.patch.object(
                        launch, "require_safe_graphics_session",
                        side_effect=launch.BolError("unsafe GPU")), \
                    mock.patch.object(launch, "_prepare_launch_engine") as prep, \
                    mock.patch.object(launch, "boot_prefix") as boot:
                with self.assertRaisesRegex(launch.BolError, "unsafe GPU"):
                    launch._launch_once()
            prep.assert_not_called()
            boot.assert_not_called()

    def test_gpu_marker_wraps_the_only_game_process_and_clears_on_return(self):
        calls = []

        class Process:
            @staticmethod
            def wait(timeout):
                calls.append(("wait", timeout))
                return 0

        def arm():
            calls.append(("arm",))
            return "owned-token"

        def popen(*_args, **_kwargs):
            calls.append(("popen",))
            return Process()

        def disarm(token):
            calls.append(("disarm", token))
            return True

        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(
                self._exercise_ready_launch(Path(td), popen, arm, disarm), 0)
        self.assertEqual(calls, [
            ("arm",),
            ("popen",),
            ("wait", 1),
            ("disarm", "owned-token"),
        ])

    def test_gpu_marker_is_cleared_when_process_spawn_fails(self):
        calls = []

        def arm():
            calls.append("arm")
            return "owned-token"

        def popen(*_args, **_kwargs):
            calls.append("popen")
            raise OSError("spawn interrupted")

        def disarm(_token):
            calls.append("disarm")
            return True

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(OSError, "spawn interrupted"):
                self._exercise_ready_launch(Path(td), popen, arm, disarm)
        self.assertEqual(calls, ["arm", "popen", "disarm"])

    def test_gpu_marker_remains_when_wrapper_returns_with_live_children(self):
        calls = []

        class Process:
            @staticmethod
            def wait(timeout):
                calls.append(("wait", timeout))
                return 0

        def arm():
            calls.append(("arm",))
            return "owned-token"

        def popen(*_args, **_kwargs):
            calls.append(("popen",))
            return Process()

        def disarm(token):
            calls.append(("disarm", token))
            return True

        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(self._exercise_ready_launch(
                Path(td), popen, arm, disarm, prefix_idle=False), 0)
        self.assertEqual(calls, [
            ("arm",),
            ("popen",),
            ("wait", 1),
        ])

    def test_wrapper_return_requires_three_idle_rescans_without_killing(self):
        scans = [[91], [91], [], [], []]
        with mock.patch.object(launch, "active_prefix",
                               return_value=Path("/tmp/prefix")), \
                mock.patch.object(launch, "prefix_processes",
                                  side_effect=scans) as processes, \
                mock.patch.object(launch.time, "monotonic",
                                  side_effect=[0, 0.1, 0.2, 0.3, 0.4]), \
                mock.patch.object(launch.time, "sleep"), \
                mock.patch.object(launch.os, "kill") as kill:
            self.assertTrue(launch._prefix_stably_idle_after_wrapper())
        self.assertEqual(processes.call_count, 5)
        kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()

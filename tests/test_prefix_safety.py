"""Regression tests for prefix shutdown and operation serialization."""
# SPDX-License-Identifier: MIT

import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from bol import gamesetup, prefix
from bol.log import BolError


class PrefixShutdownTests(unittest.TestCase):
    def test_unsafe_fresh_prefix_is_rejected_before_umu_or_wine(self):
        with tempfile.TemporaryDirectory() as td:
            pfx = Path(td) / "fresh-prefix"
            with mock.patch(
                    "bol.gpu_safety.require_safe_graphics_session",
                    side_effect=BolError("unsafe graphics")) as safety, \
                    mock.patch.object(prefix, "proton_umu_cmd") as umu, \
                    mock.patch.object(prefix.subprocess, "run") as run:
                with self.assertRaisesRegex(BolError, "unsafe graphics"):
                    prefix.boot_prefix(pfx)
            safety.assert_called_once_with()
            umu.assert_not_called()
            run.assert_not_called()

    def test_shutdown_rescans_and_terminates_new_children(self):
        scans = [[10], [10, 11], []]
        with mock.patch.object(
                prefix, "prefix_processes", side_effect=scans), \
                mock.patch.object(prefix.os, "kill") as kill, \
                mock.patch.object(prefix.time, "sleep"):
            stopped, forced = prefix.stop_prefix_procs(
                Path("/tmp/bol-prefix"), grace=5)

        self.assertEqual((stopped, forced), (2, 0))
        self.assertEqual(
            kill.call_args_list,
            [mock.call(10, 15), mock.call(11, 15)],
        )

    def test_shutdown_fails_if_process_survives_sigkill(self):
        with mock.patch.object(prefix, "prefix_processes",
                               return_value=[10]), \
                mock.patch.object(prefix.os, "kill") as kill:
            with self.assertRaisesRegex(
                    BolError, "refusing unsafe offline changes"):
                prefix.stop_prefix_procs(
                    Path("/tmp/bol-prefix"), grace=0, kill_grace=0)

        self.assertIn(mock.call(10, 15), kill.call_args_list)
        self.assertIn(mock.call(10, 9), kill.call_args_list)

    def test_wineboot_propagates_shutdown_failure(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(prefix, "LOGS", Path(td) / "logs"), \
                mock.patch.object(
                    prefix, "proton_umu_cmd",
                    return_value=(["umu", "wineboot"], {})), \
                mock.patch("bol.gpu_safety.require_safe_graphics_session"), \
                mock.patch.object(prefix.subprocess, "run"), \
                mock.patch.object(
                    prefix, "stop_prefix_procs",
                    side_effect=BolError("wineserver survived")):
            with self.assertRaisesRegex(BolError, "wineserver survived"):
                prefix.boot_prefix(Path(td) / "pfx")


class PrefixOperationLockTests(unittest.TestCase):
    def test_repair_cannot_run_while_common_lock_is_held(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(prefix, "DATA", Path(td)), \
                mock.patch.object(prefix, "stop_prefix_procs") as stop, \
                mock.patch.object(prefix.shutil, "rmtree") as rmtree:
            with prefix.prefix_operation_lock("test operation"):
                with self.assertRaisesRegex(BolError, "another BedrockOnLinux"):
                    prefix.reset_prefix()

        stop.assert_not_called()
        rmtree.assert_not_called()

    def test_setup_holds_the_same_operation_lock(self):
        events = []

        @contextmanager
        def locked(_operation):
            events.append("lock-enter")
            try:
                yield
            finally:
                events.append("lock-exit")

        with mock.patch.object(gamesetup, "prefix_operation_lock", locked), \
                mock.patch.object(
                    gamesetup, "_do_setup",
                    side_effect=lambda *args: events.append("setup") or "done"):
            self.assertEqual(gamesetup.do_setup(), "done")

        self.assertEqual(events, ["lock-enter", "setup", "lock-exit"])


if __name__ == "__main__":
    unittest.main()

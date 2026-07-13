"""Doctor integration tests for the persistent GPU safety interlock."""
# SPDX-License-Identifier: MIT

import contextlib
import sys
import unittest
from unittest import mock

from bol import cli, doctor


class DoctorGpuSafetyTests(unittest.TestCase):
    def test_acknowledgement_is_serialized_and_requires_idle_prefix(self):
        with mock.patch("bol.prefix.launch_lock",
                        return_value=contextlib.nullcontext()) as lock, \
                mock.patch("bol.prefix.active_prefix",
                           return_value="/tmp/prefix"), \
                mock.patch("bol.prefix.prefix_processes", return_value=[]), \
                mock.patch.object(doctor, "acknowledge_gpu_safety_incident",
                                  return_value=True) as acknowledge, \
                mock.patch.object(doctor, "warn"):
            self.assertTrue(doctor._acknowledge_gpu_crash())
        lock.assert_called_once_with()
        acknowledge.assert_called_once_with()

    def test_acknowledgement_refuses_live_wine_or_umu_processes(self):
        with mock.patch("bol.prefix.launch_lock",
                        return_value=contextlib.nullcontext()), \
                mock.patch("bol.prefix.active_prefix",
                           return_value="/tmp/prefix"), \
                mock.patch("bol.prefix.prefix_processes",
                           return_value=[12, 34]), \
                mock.patch.object(doctor, "acknowledge_gpu_safety_incident") \
                as acknowledge, \
                mock.patch.object(doctor, "warn"):
            self.assertFalse(doctor._acknowledge_gpu_crash())
        acknowledge.assert_not_called()

    def test_acknowledgement_does_not_turn_current_graphics_failure_green(self):
        with mock.patch.object(doctor, "_acknowledge_gpu_crash",
                               return_value=True), \
                mock.patch.object(doctor.deps, "have", return_value=True), \
                mock.patch.object(doctor.shutil, "which",
                                  return_value="/usr/bin/fake"), \
                mock.patch.object(doctor, "graphics_safety_problem",
                                  return_value="zero RandR GPU providers"), \
                mock.patch.object(doctor, "info"), \
                mock.patch.object(doctor, "ok"), \
                mock.patch.object(doctor, "warn"):
            self.assertFalse(doctor.doctor(acknowledge_gpu_crash=True))

    def test_cli_exposes_explicit_acknowledgement_option(self):
        with mock.patch.object(sys, "argv", [
                "bedrock-on-linux", "doctor", "--acknowledge-gpu-crash"]), \
                mock.patch.object(cli, "doctor", return_value=True) as run:
            with self.assertRaises(SystemExit) as exited:
                cli.main()
        self.assertEqual(exited.exception.code, 0)
        run.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()

"""Regression tests for post-mortem freeze diagnostics."""
# SPDX-License-Identifier: MIT

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bol import gamesetup


class FreezeDiagnosisTests(unittest.TestCase):
    def test_unsupported_dgc_signature_reports_compatibility_engine(self):
        with tempfile.TemporaryDirectory() as td:
            logs = Path(td)
            (logs / "proton.log").write_text(
                "d3d12_command_signature_create: Device generated commands "
                "is not supported by implementation.\n",
                encoding="utf-8",
            )
            with mock.patch.object(gamesetup, "LOGS", logs), \
                    mock.patch.object(gamesetup, "msa_signed_in",
                                      return_value=True), \
                    mock.patch.object(gamesetup, "warn"), \
                    mock.patch.object(gamesetup, "info"):
                hits = gamesetup.diagnose()
        self.assertEqual(len(hits), 1)
        self.assertIn("current compatibility engine", hits[0])


class OnlineDiagnosisTests(unittest.TestCase):
    def _diagnose(self, log, settings):
        with tempfile.TemporaryDirectory() as td:
            logs = Path(td)
            (logs / "proton.log").write_text(log, encoding="utf-8")
            with mock.patch.object(gamesetup, "LOGS", logs), \
                    mock.patch.object(gamesetup, "msa_signed_in",
                                      return_value=True), \
                    mock.patch.object(gamesetup, "load_settings",
                                      return_value=settings), \
                    mock.patch.object(gamesetup, "warn"), \
                    mock.patch.object(gamesetup, "info"):
                return gamesetup.diagnose()

    def test_native_identity_missing_after_preauth_is_reported(self):
        hits = self._diagnose(
            "preauth: loaded user/XSTS tokens\n",
            {"force_msa_facet": False},
        )
        self.assertTrue(any("native XGame identity" in hit for hit in hits))

    def test_native_identity_and_preauth_produce_no_auth_warning(self):
        hits = self._diagnose(
            "native XGame identity loaded: TitleId 0x35760c07\n"
            "preauth: loaded user/XSTS tokens\n",
            {"force_msa_facet": False},
        )
        self.assertFalse(any("server" in hit.lower() or "xbox" in hit.lower()
                             for hit in hits))

    def test_normal_uninitialize_stub_is_not_a_missing_xuser(self):
        hits = self._diagnose(
            "00e0:trace:xgameruntime:UninitializeApiImpl stub!\n",
            {},
        )
        self.assertFalse(any("no WineGDK XUser" in hit for hit in hits))

    def test_xuser_stub_still_reports_missing_runtime(self):
        hits = self._diagnose(
            "00e0:fixme:xgameruntime:XUserAddAsync stub!\n",
            {},
        )
        self.assertTrue(any("no WineGDK XUser" in hit for hit in hits))

    def test_large_log_keeps_initialization_proof_and_tail(self):
        log = (
            "native XGame identity loaded: TitleId 0x35760c07\n"
            "preauth: loaded user/XSTS credentials\n"
            + "middle\n" * 70000
            + "00e0:trace:xgameruntime:UninitializeApiImpl stub!\n"
        )
        hits = self._diagnose(log, {})
        self.assertFalse(any("no WineGDK XUser" in hit for hit in hits))

    def test_nv_dgc_raw_va_error_reports_compatibility_engine(self):
        with tempfile.TemporaryDirectory() as td:
            logs = Path(td)
            (logs / "proton.log").write_text(
                "d3d12_command_signature_init_state_template_dgc_nv: "
                "Root parameter 2 is not a raw VA. Cannot implement command "
                "signature.\n",
                encoding="utf-8",
            )
            with mock.patch.object(gamesetup, "LOGS", logs), \
                    mock.patch.object(gamesetup, "msa_signed_in",
                                      return_value=True), \
                    mock.patch.object(gamesetup, "warn"), \
                    mock.patch.object(gamesetup, "info"):
                hits = gamesetup.diagnose()
        self.assertEqual(len(hits), 1)
        self.assertIn("current compatibility engine", hits[0])


if __name__ == "__main__":
    unittest.main()

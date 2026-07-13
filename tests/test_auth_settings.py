"""Regression tests for the managed WineGDK online-access setting."""
# SPDX-License-Identifier: MIT

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bol import auth


MANAGED_STAMP = f"winegdk:{auth.WINEGDK_BUILD_REV}"


class ForceMsaFacetSettingsTests(unittest.TestCase):
    def _enabled(self, settings):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(auth, "load_settings",
                                  return_value=settings), \
                mock.patch.object(auth, "save_settings") as save, \
                mock.patch.object(auth, "info"):
            result = auth.force_msa_facet_enabled()
        return result, save

    def test_legacy_disabled_value_is_reenabled_for_guarded_engine(self):
        settings = {
            "proton_source": "winegdk",
            "force_msa_facet": False,
        }
        enabled, save = self._enabled(settings)
        self.assertTrue(enabled)
        self.assertTrue(settings["force_msa_facet"])
        self.assertEqual(settings["force_msa_facet_engine_rev"],
                         MANAGED_STAMP)
        save.assert_called_once_with(settings)

    def test_disabled_choice_for_current_engine_is_respected(self):
        settings = {
            "proton_source": "winegdk",
            "force_msa_facet": False,
            "force_msa_facet_engine_rev": MANAGED_STAMP,
        }
        enabled, save = self._enabled(settings)
        self.assertFalse(enabled)
        save.assert_not_called()

    def test_disabled_choice_is_retried_after_engine_upgrade(self):
        settings = {
            "proton_source": "winegdk",
            "force_msa_facet": False,
            "force_msa_facet_engine_rev": "winegdk:wow64-archs-r10",
        }
        enabled, save = self._enabled(settings)
        self.assertTrue(enabled)
        save.assert_called_once_with(settings)

    def test_custom_engine_choice_is_not_migrated(self):
        settings = {
            "proton_source": "custom",
            "force_msa_facet": False,
        }
        enabled, save = self._enabled(settings)
        self.assertFalse(enabled)
        save.assert_not_called()

    def test_legacy_custom_proton_dir_is_not_migrated_as_managed(self):
        settings = {
            "proton_dir": "/opt/custom-proton",
            "force_msa_facet": False,
        }
        enabled, save = self._enabled(settings)
        self.assertFalse(enabled)
        save.assert_not_called()

    def test_environment_escape_hatch_is_non_persistent(self):
        with mock.patch.dict(os.environ,
                             {"BOL_DISABLE_SERVER_PATCHES": "yes"}, clear=True), \
                mock.patch.object(auth, "load_settings") as load, \
                mock.patch.object(auth, "save_settings") as save, \
                mock.patch.object(auth, "warn"):
            self.assertFalse(auth.force_msa_facet_enabled())
        load.assert_not_called()
        save.assert_not_called()

    def test_explicit_choice_is_stamped_with_current_engine(self):
        settings = {"proton_source": "winegdk"}
        with mock.patch.object(auth, "load_settings",
                               return_value=settings), \
                mock.patch.object(auth, "save_settings") as save:
            auth.set_force_msa_facet(False)
        self.assertFalse(settings["force_msa_facet"])
        self.assertEqual(settings["force_msa_facet_engine_rev"],
                         MANAGED_STAMP)
        save.assert_called_once_with(settings)

    def test_registry_prerequisite_uses_resolved_online_setting(self):
        prefix = Path("/tmp/bol-prefix")
        with mock.patch.object(auth, "force_msa_facet_enabled",
                               return_value=True), \
                mock.patch.object(auth, "active_prefix", return_value=prefix), \
                mock.patch.object(auth, "load_settings", return_value={}), \
                mock.patch.object(auth, "update_prefix_registry") as update:
            auth.wine_apply_winegdk_prereqs()

        update.assert_called_once()
        self.assertEqual(update.call_args.args[0], prefix)
        force = [change for change in update.call_args.kwargs["machine"]
                 if change.name == "ForceMsaFacet"]
        self.assertEqual(len(force), 1)
        self.assertEqual(force[0].value, 1)

    def test_registry_failure_blocks_a_misconfigured_online_launch(self):
        with mock.patch.object(auth, "force_msa_facet_enabled",
                               return_value=True), \
                mock.patch.object(auth, "active_prefix",
                                  return_value=Path("/tmp/bol-prefix")), \
                mock.patch.object(auth, "load_settings", return_value={}), \
                mock.patch.object(auth, "update_prefix_registry",
                                  side_effect=OSError("injected")), \
                mock.patch.object(auth, "warn"), \
                mock.patch.object(auth, "err"):
            with self.assertRaisesRegex(auth.BolError, "offline WineGDK"):
                auth.wine_apply_winegdk_prereqs()

    def test_refresh_token_write_never_starts_wine(self):
        prefix = Path("/tmp/bol-prefix")
        with mock.patch.object(auth, "active_prefix", return_value=prefix), \
                mock.patch.object(auth, "update_prefix_registry") as update:
            self.assertTrue(auth.wine_reg_set_refresh_token("opaque-token"))
        update.assert_called_once()
        change = update.call_args.kwargs["machine"][0]
        self.assertEqual(change.key, auth.WINEGDK_REG)
        self.assertEqual(change.name, "RefreshToken")
        self.assertEqual(change.value, "opaque-token")


class OnlinePreauthPayloadTests(unittest.TestCase):
    @staticmethod
    def payload(expiry="2999-01-01T00:00:00Z"):
        return {
            "device_token": "device",
            "device_token_expiry": expiry,
            "user_token": "user",
            "user_token_expiry": expiry,
            "xbl_token": "xbl",
            "xbl_token_expiry": expiry,
            "xbl_xuid": "1234",
            "sisu_token": "playfab",
            "sisu_rp": "https://example.playfabapi.com/",
            "sisu_uhs": "42",
            "sisu_expiry": expiry,
            "mp_token": "multiplayer",
            "mp_rp": "https://multiplayer.minecraft.net/",
            "mp_uhs": "42",
            "mp_expiry": expiry,
        }

    def test_complete_future_payload_is_ready(self):
        self.assertEqual(auth._online_preauth_problems(self.payload()), [])

    def test_xbox_seven_digit_expiry_is_python39_compatible(self):
        # Xbox NotAfter uses 100 ns precision. Python 3.9's fromisoformat()
        # accepts at most six fractional digits, so the launcher must normalize
        # this real service format before parsing it.
        service_expiry = "2999-01-01T00:00:00.1234567Z"
        self.assertEqual(
            auth._normalize_xbox_expiry(service_expiry),
            "2999-01-01T00:00:00.123456+00:00",
        )
        payload = self.payload(service_expiry)
        self.assertEqual(auth._online_preauth_problems(payload), [])

    def test_missing_multiplayer_token_is_rejected(self):
        payload = self.payload()
        payload["mp_token"] = None
        self.assertIn("missing mp_token",
                      auth._online_preauth_problems(payload))

    def test_expired_token_is_rejected(self):
        problems = auth._online_preauth_problems(
            self.payload("2000-01-01T00:00:00Z"))
        self.assertIn("expired mp_token", problems)

    def test_partial_payload_never_replaces_existing_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "device.json"
            path.write_text("keep-me")
            payload = self.payload()
            payload["xbl_token"] = None
            self.assertFalse(auth._store_online_preauth(path, payload))
            self.assertEqual(path.read_text(), "keep-me")

    def test_complete_payload_is_written_atomically_and_private(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "device.json"
            self.assertTrue(auth._store_online_preauth(path, self.payload()))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(auth._load_online_preauth(path)["mp_token"],
                             "multiplayer")

    def test_corrupt_or_unreadable_account_epoch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = root / "winegdk-preauth"
            cache.mkdir()
            path = cache / "device.json"
            payload = self.payload()
            self.assertTrue(auth._store_online_preauth(path, payload))
            before = path.read_bytes()

            (cache / ".account-epoch").write_text("not-a-valid-generation\n")
            self.assertIsNone(auth._account_cache_epoch(cache))
            self.assertFalse(auth._store_online_preauth(path, payload))
            with mock.patch.object(auth, "DATA", root), \
                    mock.patch.object(auth, "warn"):
                self.assertFalse(auth.xbl_preauth(""))
            self.assertEqual(path.read_bytes(), before)

            # Permission/read failures use the same fail-closed state and may
            # neither match an old payload nor authorize a new store.
            with mock.patch.object(auth, "_account_cache_epoch",
                                   return_value=None):
                self.assertFalse(auth._cached_account_matches(payload, None))
                self.assertFalse(auth._store_online_preauth(path, payload))
            self.assertEqual(path.read_bytes(), before)

    def test_missing_access_token_reuses_complete_unexpired_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = root / "winegdk-preauth"
            cache.mkdir()
            auth._store_online_preauth(cache / "device.json", self.payload())
            with mock.patch.object(auth, "DATA", root), \
                    mock.patch.object(auth, "warn"), \
                    mock.patch.object(auth, "info"):
                self.assertTrue(auth.xbl_preauth(""))

    def test_missing_access_token_does_not_accept_partial_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = root / "winegdk-preauth"
            cache.mkdir()
            partial = self.payload()
            partial["mp_token"] = None
            path = cache / "device.json"
            path.write_text(json.dumps(partial))
            before = path.read_bytes()
            with mock.patch.object(auth, "DATA", root), \
                    mock.patch.object(auth, "warn"), \
                    mock.patch.object(auth, "info"):
                self.assertFalse(auth.xbl_preauth(""))
            self.assertEqual(path.read_bytes(), before)

    def test_launch_epoch_mismatch_refuses_even_valid_cached_tokens(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = root / "winegdk-preauth"
            cache.mkdir()
            current_epoch = "c" * 32
            (cache / ".account-epoch").write_text(current_epoch + "\n")
            payload = self.payload()
            payload["_account_epoch"] = current_epoch
            auth._store_online_preauth(cache / "device.json", payload,
                                       expected_epoch=current_epoch)

            with mock.patch.object(auth, "DATA", root), \
                    mock.patch.object(auth, "warn"):
                self.assertFalse(auth.xbl_preauth("", "d" * 32))

    def test_logout_purges_account_tokens_but_keeps_device_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            msa = root / "msa"
            cache = root / "winegdk-preauth"
            msa.mkdir()
            cache.mkdir()
            (msa / "token.json").write_text(
                json.dumps({"refresh_token": "old-account"}))
            old_payload = self.payload()
            auth._store_online_preauth(cache / "device.json", old_payload)
            key = b"device-private-key"
            device_id = "{stable-device-id}"
            (cache / "device-key.pem").write_bytes(key)
            (cache / "device-id.txt").write_text(device_id)
            (cache / ".device-crash.tmp").write_text("old account tokens")

            with mock.patch.object(auth, "DATA", root), \
                    mock.patch.object(auth, "MSA_DIR", msa):
                self.assertTrue(auth.msa_logout())

            self.assertFalse((msa / "token.json").exists())
            self.assertFalse((cache / "device.json").exists())
            self.assertFalse((cache / ".device-crash.tmp").exists())
            self.assertEqual((cache / "device-key.pem").read_bytes(), key)
            self.assertEqual((cache / "device-id.txt").read_text(), device_id)
            self.assertRegex((cache / ".account-epoch").read_text().strip(),
                             r"^[0-9a-f]{32}$")

            # Even if an old cache is restored after a crash, its legacy epoch
            # cannot be consumed by the next account.
            (cache / "device.json").write_text(json.dumps(old_payload))
            with mock.patch.object(auth, "DATA", root), \
                    mock.patch.object(auth, "warn"), \
                    mock.patch.object(auth, "info"):
                self.assertFalse(auth.xbl_preauth(""))

    def test_fallback_rechecks_cache_expiry_after_failed_post(self):
        from datetime import datetime, timezone

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = root / "winegdk-preauth"
            cache.mkdir()
            expiry_text = "2030-01-01T00:00:00.1234567Z"
            expiry = datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp()
            auth._store_online_preauth(
                cache / "device.json", self.payload(expiry_text))

            # First validation: two minutes remain. The device POST then fails
            # after the cache has crossed its 60-second safety margin. A stale
            # boolean from function entry would incorrectly return True here.
            with mock.patch.object(auth, "DATA", root), \
                    mock.patch.object(
                        auth.time, "time",
                        side_effect=[expiry - 120, expiry - 30, expiry]), \
                    mock.patch("urllib.request.urlopen",
                               side_effect=OSError("simulated timeout")), \
                    mock.patch.object(auth, "warn"), \
                    mock.patch.object(auth, "info"):
                self.assertFalse(auth.xbl_preauth("fresh-access-token"))


class NativeAuthCancellationTests(unittest.TestCase):
    @staticmethod
    def _device_response():
        return {
            "device_code": "device-code",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://example.invalid/link",
            "interval": 1,
            "expires_in": 900,
        }

    def test_logout_during_token_post_cannot_resurrect_account(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = root / "winegdk-preauth"
            msa = root / "msa"
            cache.mkdir()
            msa.mkdir()
            epoch = "a" * 32
            (cache / ".account-epoch").write_text(epoch + "\n")
            native = auth.NativeAuth()
            online = mock.Mock()

            def post(url, _data):
                if url == auth.MSA_CONNECT:
                    return self._device_response()
                # Sign out completes while the token POST is in flight.
                auth.msa_logout()
                return {"refresh_token": "must-not-survive"}

            with mock.patch.object(auth, "DATA", root), \
                    mock.patch.object(auth, "MSA_DIR", msa), \
                    mock.patch.object(auth, "http_post_form",
                                      side_effect=post), \
                    mock.patch.object(auth.time, "sleep"), \
                    mock.patch.object(auth, "warn"), \
                    mock.patch.object(auth, "info"):
                native._flow(None, online, epoch)

            self.assertFalse((msa / "token.json").exists())
            self.assertFalse(native.online)
            online.assert_not_called()
            self.assertNotEqual(
                (cache / ".account-epoch").read_text().strip(), epoch)

    def test_stop_during_token_post_discards_response(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = root / "winegdk-preauth"
            msa = root / "msa"
            cache.mkdir()
            msa.mkdir()
            epoch = "b" * 32
            (cache / ".account-epoch").write_text(epoch + "\n")
            native = auth.NativeAuth()

            def post(url, _data):
                if url == auth.MSA_CONNECT:
                    return self._device_response()
                native.stop()
                return {"refresh_token": "cancelled"}

            with mock.patch.object(auth, "DATA", root), \
                    mock.patch.object(auth, "MSA_DIR", msa), \
                    mock.patch.object(auth, "http_post_form",
                                      side_effect=post), \
                    mock.patch.object(auth.time, "sleep"), \
                    mock.patch.object(auth, "info"):
                native._flow(None, None, epoch)

            self.assertFalse((msa / "token.json").exists())
            self.assertFalse(native.online)


if __name__ == "__main__":
    unittest.main()

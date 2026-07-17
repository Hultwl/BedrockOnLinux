"""Keep the native WineGDK Xbox and file-picker delta reproducible."""
# SPDX-License-Identifier: MIT

import hashlib
import re
import unittest
from pathlib import Path

from bol.config import WINEGDK_SOURCE_COMMIT


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build-winegdk-bullseye.sh"
PACKAGER = ROOT / "scripts/package-engine.sh"
BASE_PATCH = (ROOT / "third_party/winegdk-r12" /
              "online-patches-after-user-ready.patch")
DELTA = ROOT / "third_party/winegdk-native5"
PATCH = DELTA / "0001-winegdk-native5-Xbox-and-file-picker-runtime.patch"
SOURCE_SUMS = DELTA / "SOURCE-SHA256SUMS"
CHANGED_FILES = {
    "dlls/windows.storage/Makefile.in",
    "dlls/windows.storage/classes.idl",
    "dlls/windows.storage/main.c",
    "dlls/windows.storage/pickers.c",
    "dlls/windows.storage/private.h",
    "dlls/windows.storage/tests/storage.c",
    "dlls/windows.storage/vector.c",
    "dlls/xgameruntime/GDKComponent/System/User/XUser.c",
    "dlls/xgameruntime/GDKComponent/System/User/XUser.h",
    "dlls/xgameruntime/GDKComponent/System/User/DeviceAuth.c",
    "dlls/xgameruntime/GDKComponent/System/User/DeviceAuth.h",
    "dlls/xgameruntime/GDKComponent/System/User/Token.c",
    "dlls/xgameruntime/GDKComponent/InitInternalGDKC.c",
    "dlls/xgameruntime/GDKComponent/System/XGame.c",
    "dlls/xgameruntime/GDKComponent/System/XSystem.c",
    "dlls/xgameruntime/Makefile.in",
    "dlls/xgameruntime/main.c",
    "dlls/xgameruntime/private.h",
    "dlls/xgameruntime/tests/xgameruntime.c",
    "include/Makefile.in",
    "include/microsoft.ui.idl",
    "include/microsoft.windows.storage.pickers.idl",
    "include/xgame.idl",
    "include/xgameerr.h",
}


class WineGdkSourceDeltaTests(unittest.TestCase):
    def _constant(self, name):
        match = re.search(
            rf'^readonly {name}="([^"]+)"', SCRIPT.read_text(), re.MULTILINE)
        self.assertIsNotNone(match, name)
        return match.group(1)

    def test_builder_pins_target_base_patch_and_all_changed_sources(self):
        self.assertEqual(self._constant("EXPECTED_COMMIT"),
                         WINEGDK_SOURCE_COMMIT)
        self.assertRegex(self._constant("PUBLIC_BASE_COMMIT"),
                         r"^[0-9a-f]{40}$")
        self.assertEqual(
            hashlib.sha256(BASE_PATCH.read_bytes()).hexdigest(),
            self._constant("VENDORED_BASE_PATCH_SHA256"),
        )
        self.assertEqual(
            hashlib.sha256(PATCH.read_bytes()).hexdigest(),
            self._constant("VENDORED_PATCH_SHA256"),
        )
        self.assertEqual(
            hashlib.sha256(SOURCE_SUMS.read_bytes()).hexdigest(),
            self._constant("SOURCE_SHA256SUMS_SHA256"),
        )
        pinned = {
            line.split("  ", 1)[1]
            for line in SOURCE_SUMS.read_text().splitlines() if line
        }
        self.assertEqual(pinned, CHANGED_FILES)

    def test_patch_completes_native_context_and_file_picker_without_patcher(self):
        text = PATCH.read_text()
        self.assertTrue(text.startswith(f"From {WINEGDK_SOURCE_COMMIT} "))
        changed = {
            left for left, right in re.findall(
                r"^diff --git a/(\S+) b/(\S+)$", text, re.MULTILINE)
            if left == right
        }
        self.assertEqual(changed, CHANGED_FILES)

        additions = "\n".join(
            line[1:] for line in text.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        self.assertIn("WineGDKLoadGameConfig", additions)
        self.assertIn("XUserGetTokenAndSignatureUtf16Data", additions)
        self.assertIn("xbl_privileges", additions)
        self.assertIn("if (sandboxIdUsed)", additions)
        self.assertIn("native Xbox app configuration ready", additions)
        self.assertIn("*maxUsers = 1", additions)
        self.assertIn("XUserGamertagComponent_ModerSuffix", additions)
        self.assertIn("result_token_len + 1", additions)
        self.assertIn("result_token_utf16_count * sizeof(WCHAR)", additions)
        self.assertIn("performing native InitializeApiImplEx2 one-time attempt",
                      additions)
        self.assertIn("INIT_ONCE", additions)
        self.assertIn("realms_token", additions)
        self.assertIn("https://pocket.realms.minecraft.net/", additions)
        self.assertIn("pocket.realms.minecraft.net", additions)
        self.assertIn("bedrock.frontend.realms.minecraft-services.net",
                      additions)
        self.assertIn("bedrock.frontendlegacy.realms.minecraft-services.net",
                      additions)
        self.assertIn(
            "RuntimeClass_Microsoft_Windows_Storage_Pickers_FileOpenPicker",
            additions,
        )
        self.assertIn("IFileOpenPickerFactory", additions)
        self.assertIn("PickSingleFileAsync", additions)
        self.assertIn("PickMultipleFilesAsync", additions)
        self.assertIn("FOS_ALLOWMULTISELECT", additions)
        self.assertIn("CLSID_FileOpenDialog", additions)
        self.assertIn("IPickFileResult_AddRef( *results = operation->result )",
                      additions)
        self.assertNotIn("payments.realms.minecraft-services.net", additions)
        self.assertNotIn("WineGDKApplyOnlinePatches", additions)
        self.assertNotIn("VirtualProtect", additions)
        self.assertNotIn("GetModuleInformation", additions)

        deletions = "\n".join(
            line[1:] for line in PATCH.read_text().splitlines()
            if line.startswith("-") and not line.startswith("---")
        )
        self.assertIn("WineGDKApplyOnlinePatches", deletions)
        self.assertIn("VirtualProtect", deletions)

    def test_builder_replays_reviewed_r12_then_native_delta(self):
        text = SCRIPT.read_text()
        self.assertIn('apply --check "$VENDORED_BASE_PATCH"', text)
        self.assertIn('apply --check "$VENDORED_PATCH"', text)
        self.assertLess(text.index('apply "$VENDORED_BASE_PATCH"'),
                        text.index('apply --check "$VENDORED_PATCH"'))

    def test_builder_can_finalize_the_verified_prefix_after_install(self):
        text = SCRIPT.read_text()
        self.assertIn(
            'local work_root="$1"\n  local prefix="$work_root/prefix"',
            text,
        )
        self.assertIn(
            'BOL_WINEGDK_INTERNAL=1 "$SCRIPT_PATH" --internal-finalize '
            '"$WORK_ROOT"',
            text,
        )

    def test_packager_overlays_prefix_only_after_isolated_snapshot(self):
        text = PACKAGER.read_text()
        snapshot = 'cp -al "$ENGINE_DIR/." "$STAGED_ENGINE/"'
        overlay = (
            'cp -a --remove-destination "$WINEGDK_PREFIX/." '
            '"$STAGED_ENGINE/files/"'
        )
        self.assertIn(snapshot, text)
        self.assertIn(overlay, text)
        self.assertLess(text.index(snapshot), text.index(overlay))

    def test_packager_requires_native_app_context_in_both_architectures(self):
        text = PACKAGER.read_text()
        arch_loop = text.index('for arch in "${ARCHES[@]}"; do',
                               text.index("# The native engine must expose"))
        marker = text.index(
            'has_text "$xgdk" "native Xbox app configuration ready"',
            arch_loop,
        )
        loop_end = text.index("\ndone", marker)
        self.assertLess(arch_loop, marker)
        self.assertLess(marker, loop_end)


if __name__ == "__main__":
    unittest.main()

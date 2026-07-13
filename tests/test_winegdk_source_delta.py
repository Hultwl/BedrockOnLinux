"""Keep the unpublished r11 source delta independently reproducible."""
# SPDX-License-Identifier: MIT

import hashlib
import re
import unittest
from pathlib import Path

from bol.config import WINEGDK_SOURCE_COMMIT


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build-winegdk-bullseye.sh"
PATCH = ROOT / "third_party/winegdk-r11/signin-rdx-guard.patch"


class WineGdkSourceDeltaTests(unittest.TestCase):
    def test_builder_pins_target_base_patch_and_result(self):
        script = SCRIPT.read_text()
        # Keep explicit extraction readable when a constant is renamed.
        def constant(name):
            match = re.search(
                rf'^readonly {name}="([^"]+)"', script, re.MULTILINE)
            self.assertIsNotNone(match, name)
            return match.group(1)

        self.assertEqual(constant("EXPECTED_COMMIT"), WINEGDK_SOURCE_COMMIT)
        self.assertRegex(constant("PUBLIC_BASE_COMMIT"), r"^[0-9a-f]{40}$")
        self.assertRegex(constant("PATCHED_MAIN_SHA256"), r"^[0-9a-f]{64}$")
        self.assertEqual(
            hashlib.sha256(PATCH.read_bytes()).hexdigest(),
            constant("VENDORED_PATCH_SHA256"),
        )

    def test_patch_records_target_identity_and_only_one_source_file(self):
        text = PATCH.read_text()
        self.assertTrue(text.startswith(f"From {WINEGDK_SOURCE_COMMIT} "))
        changed = re.findall(r"^diff --git a/(\S+) b/(\S+)$",
                             text, re.MULTILINE)
        self.assertEqual(changed,
                         [("dlls/xgameruntime/main.c",
                           "dlls/xgameruntime/main.c")])
        self.assertIn("cave[26]=0x7e", text)


if __name__ == "__main__":
    unittest.main()

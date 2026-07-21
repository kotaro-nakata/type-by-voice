import os
import unittest
from unittest.mock import patch

import platform_backend as pb


class LinuxInjectorTests(unittest.TestCase):
    @patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland"}, clear=False)
    @patch("platform_backend.shutil.which")
    def test_wayland_prefers_ydotool_over_wtype(self, which):
        which.side_effect = lambda name: f"/usr/bin/{name}" if name in {
            "wl-copy", "wtype", "ydotool"
        } else None
        injector = pb.LinuxInjector("paste", False)
        self.assertEqual(injector.copy_cmd[0], "wl-copy")
        self.assertEqual(injector.paste_cmd[0], "ydotool")


if __name__ == "__main__":
    unittest.main()

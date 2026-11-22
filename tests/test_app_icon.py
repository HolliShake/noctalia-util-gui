import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main


class WindowIconTests(unittest.TestCase):
    def test_linux_window_uses_desktop_entry_identity(self):
        root = Mock()
        with (
                patch("main.sys.platform", "linux"),
                patch("main.ctk.set_appearance_mode"),
                patch("main.ctk.set_default_color_theme"),
                patch("main.ctk.CTk", return_value=root) as create_root,
                patch("main._set_window_icon"),
                patch("main.apply_ttk_theme"),
                patch("main.App"),
                ):
            main.main()

        create_root.assert_called_once_with(className="NoctaliaUtilGUI")

    def test_windows_uses_png_and_ico_window_icons(self):
        root = Mock()
        icon_dir = Path(main.__file__).resolve().parent / "data"
        with (
                patch("main.sys.platform", "win32"),
                patch("main.tk.PhotoImage") as photo_image):
            main._set_window_icon(root)

        photo_image.assert_called_once_with(
            file=str(icon_dir / "noctalia-util-gui.png"))
        root.iconphoto.assert_called_once_with(True, photo_image.return_value)
        root.iconbitmap.assert_called_once_with(
            str(icon_dir / "noctalia-util-gui.ico"))
        self.assertIs(root._window_icon, photo_image.return_value)

    def test_non_windows_uses_png_window_icon(self):
        root = Mock()
        with (
                patch("main.sys.platform", "linux"),
                patch("main.tk.PhotoImage") as photo_image):
            main._set_window_icon(root)

        root.iconphoto.assert_called_once_with(True, photo_image.return_value)
        root.iconbitmap.assert_not_called()
        self.assertIs(root._window_icon, photo_image.return_value)


if __name__ == "__main__":
    unittest.main()

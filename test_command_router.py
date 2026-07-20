import unittest
from unittest.mock import patch
from command_router import Command, CommandRouter
import simple_commands

class CommandRouterTests(unittest.TestCase):
 def setUp(self): self.r=CommandRouter(["コンピューター","パソコン"])
 def test_dictation(self): self.assertIsNone(self.r.parse("ブラウザを開いてください"))
 def test_app(self): self.assertEqual(self.r.parse("コンピューター、ブラウザを開いて"),Command("open_app","browser"))
 def test_search(self): self.assertEqual(self.r.parse("パソコン、猫の動画を検索して"),Command("web_search","猫の動画"))
 def test_volume(self): self.assertEqual(self.r.parse("コンピューター、音量を120パーセントにして"),Command("volume",100))
 def test_folder(self): self.assertEqual(self.r.parse("コンピューター、ダウンロードフォルダを開いて"),Command("open_folder","downloads"))
 def test_unknown(self): self.assertEqual(self.r.parse("コンピューター、宇宙船を起動して"),Command("unknown","宇宙船を起動して"))
 @patch("simple_commands.webbrowser.open")
 def test_search_executor(self,open_mock):
  ok,_=simple_commands.execute(Command("web_search","猫 動画"))
  self.assertTrue(ok); self.assertIn("%E7%8C%AB+%E5%8B%95%E7%94%BB",open_mock.call_args.args[0])

if __name__=="__main__": unittest.main()

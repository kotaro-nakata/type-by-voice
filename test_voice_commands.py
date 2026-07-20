import unittest
from unittest.mock import Mock, patch
from command_router import CommandRouter
from voice_term import App

class VoiceCommandIntegrationTests(unittest.TestCase):
 def make_app(self,enabled=True):
  app=App.__new__(App); app.commands_enabled=enabled
  app.command_router=CommandRouter(["コンピューター","パソコン"])
  app.outputter=Mock(); app.speaker=Mock(); return app
 @patch("voice_term.notify")
 def test_normal_text_is_still_dictated(self,notify):
  app=self.make_app(); app._handle_transcribed_text("通常の文章です")
  app.outputter.send.assert_called_once_with("通常の文章です")
 @patch("voice_term.notify")
 @patch("voice_term.execute_simple_command",return_value=(True,"ブラウザを開きました"))
 def test_wake_word_executes_instead_of_dictating(self,execute,notify):
  app=self.make_app(); app._handle_transcribed_text("コンピューター、ブラウザを開いて")
  execute.assert_called_once(); app.outputter.send.assert_not_called()
 @patch("voice_term.notify")
 def test_unknown_command_is_not_dictated(self,notify):
  app=self.make_app(); app._handle_transcribed_text("コンピューター、宇宙船を起動して")
  app.outputter.send.assert_not_called()

if __name__=="__main__": unittest.main()

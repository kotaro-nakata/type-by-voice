"""Allowlisted desktop actions."""
from datetime import datetime
import os,shutil,subprocess,sys,webbrowser
from pathlib import Path
from urllib.parse import quote_plus
WIN=sys.platform=="win32"; MAC=sys.platform=="darwin"
def execute(c):
 try:
  k,v=c.kind,c.value
  if k=="open_url": webbrowser.open(str(v)); return True,"URLを開きました"
  if k=="web_search": webbrowser.open("https://www.google.com/search?q="+quote_plus(str(v))); return True,f"「{v}」を検索しました"
  if k=="open_folder":
   h=Path.home(); p={"home":h,"downloads":h/"Downloads","desktop":h/"Desktop","documents":h/"Documents"}.get(v)
   if not p or not p.exists(): return False,"フォルダが見つかりません"
   _open(p); return True,f"{p.name or p}を開きました"
  if k=="open_app": return _app(v)
  if k=="volume": return _volume(v)
  if k=="time": return True,datetime.now().strftime("現在時刻は%H時%M分です")
  if k=="date": return True,datetime.now().strftime("今日は%Y年%m月%d日です")
 except Exception as e: return False,f"操作に失敗しました: {str(e)[:80]}"
 return False,"未対応のコマンドです"
def _open(x):
 if WIN: os.startfile(str(x))
 elif MAC: subprocess.Popen(["open",str(x)])
 else: subprocess.Popen(["xdg-open",str(x)])
def _app(n):
 if n=="browser": webbrowser.open("about:blank"); return True,"ブラウザを開きました"
 if n=="files": _open(Path.home()); return True,"ファイルマネージャーを開きました"
 if n=="settings":
  if WIN: os.startfile("ms-settings:")
  elif MAC: subprocess.Popen(["open","x-apple.systempreferences:"])
  elif shutil.which("gnome-control-center"): subprocess.Popen(["gnome-control-center"])
  else: return False,"この環境の設定アプリには未対応です"
  return True,"設定を開きました"
 if n=="terminal":
  if WIN: subprocess.Popen(["cmd.exe"])
  elif MAC: subprocess.Popen(["open","-a","Terminal"])
  else:
   a=next((x for x in ("x-terminal-emulator","gnome-terminal","konsole") if shutil.which(x)),None)
   if not a: return False,"ターミナルが見つかりません"
   subprocess.Popen([a])
  return True,"ターミナルを開きました"
 return False,"許可されていないアプリです"
def _volume(v):
 if not WIN and not MAC:
  if shutil.which("wpctl"):
   a=["wpctl","set-volume","@DEFAULT_AUDIO_SINK@",f"{v}%"] if isinstance(v,int) else (["wpctl","set-mute","@DEFAULT_AUDIO_SINK@","1" if v=="mute" else "0"] if v in ("mute","unmute") else ["wpctl","set-volume","@DEFAULT_AUDIO_SINK@","5%+" if v=="up" else "5%-"])
   subprocess.run(a,check=True); return True,"音量を変更しました"
  if shutil.which("pactl"):
   a=["pactl","set-sink-volume","@DEFAULT_SINK@",f"{v}%"] if isinstance(v,int) else (["pactl","set-sink-mute","@DEFAULT_SINK@","1" if v=="mute" else "0"] if v in ("mute","unmute") else ["pactl","set-sink-volume","@DEFAULT_SINK@","+5%" if v=="up" else "-5%"])
   subprocess.run(a,check=True); return True,"音量を変更しました"
 if WIN:
  try:
   from pycaw.pycaw import AudioUtilities
   e=AudioUtilities.GetSpeakers().EndpointVolume
   if isinstance(v,int): e.SetMasterVolumeLevelScalar(v/100,None)
   elif v=="mute": e.SetMute(1,None)
   elif v=="unmute": e.SetMute(0,None)
   else: e.SetMasterVolumeLevelScalar(max(0,min(1,e.GetMasterVolumeLevelScalar()+(0.05 if v=="up" else -0.05))),None)
   return True,"音量を変更しました"
  except (ImportError,AttributeError,OSError): pass
 if MAC:
  s=f"set volume output volume {v}" if isinstance(v,int) else ("set volume with output muted" if v=="mute" else ("set volume without output muted" if v=="unmute" else f"set volume output volume ((output volume of (get volume settings)) {'+ 5' if v=='up' else '- 5'})"))
  subprocess.run(["osascript","-e",s],check=True); return True,"音量を変更しました"
 if v in ("up","down","mute"):
  from pynput.keyboard import Controller,Key
  k={"up":Key.media_volume_up,"down":Key.media_volume_down,"mute":Key.media_volume_mute}[v]; c=Controller(); c.press(k); c.release(k); return True,"音量を変更しました"
 return False,"この環境では指定された音量操作に対応していません"

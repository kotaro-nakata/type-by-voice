' デスクトップに voice-term のショートカットを作成する (Windows)
' 使い方: このファイルをダブルクリック（またはcscript install_shortcut.vbs）
' パスはこのスクリプトの置き場所から自動で解決するので、クローン先はどこでもよい。

Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)

Set ws = CreateObject("WScript.Shell")
desktop = ws.SpecialFolders("Desktop")

Set lnk = ws.CreateShortcut(desktop & "\Voice Term.lnk")
lnk.TargetPath = root & "\run_windows.bat"
lnk.WorkingDirectory = root
lnk.IconLocation = root & "\voice-term.ico,0"
lnk.WindowStyle = 7  ' 最小化で起動（batのコンソールを目立たせない）
lnk.Description = "voice-term: voice typing (starts in system tray)"
lnk.Save

MsgBox "デスクトップに「Voice Term」を作成しました。", vbInformation, "voice-term"

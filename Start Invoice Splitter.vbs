' Start Invoice Splitter with no terminal window (Windows)
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir

' Prefer pythonw (no console); fall back to py -3
cmd = "pyw -3 run_ui.py --launch"
exitCode = sh.Run(cmd, 0, True)
If exitCode <> 0 Then
  sh.Run "py -3 run_ui.py --launch", 0, True
End If

' Opens the Vue launcher menu directly, without a console window.
' structura-react's version chooser runs this script for "Ouvrir Vue", so it
' must not open the chooser again: the Start menu shortcut and
' lancer_structura.bat are the entry points that offer both versions.
Option Explicit

Dim files, project, python, script, shell
Set files = CreateObject("Scripting.FileSystemObject")
project = files.GetParentFolderName(WScript.ScriptFullName)
python = files.BuildPath(project, ".venv\Scripts\pythonw.exe")
script = files.BuildPath(project, "scripts\launch_structura.py")

If Not files.FileExists(python) Or Not files.FileExists(script) Then
    MsgBox "Le lanceur ou l'environnement Python de Structura est introuvable.", vbCritical, "Structura"
    WScript.Quit 1
End If

Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = project
shell.Run Quote(python) & " " & Quote(script) & " --vue", 1, False

Function Quote(value)
    Quote = Chr(34) & value & Chr(34)
End Function

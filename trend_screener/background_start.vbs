Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c ""cd /d E:\claude\trend_screener && start http://localhost:5000 && python server.py""", 0, False

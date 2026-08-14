@echo off
setlocal
cd /d "%~dp0..\.."
"C:\Users\70918\AppData\Local\Programs\Python\Python313\python.exe" -m zotero_mineru_sync %*
exit /b %ERRORLEVEL%

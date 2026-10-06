@echo off
rem explainer CLI launcher. Uses %EXPLAINER_PYTHON% if set, else python on PATH.
setlocal
if defined EXPLAINER_PYTHON (set "PY=%EXPLAINER_PYTHON%") else (set "PY=python")
"%PY%" "%~dp0explainer\cli.py" %*
exit /b %ERRORLEVEL%

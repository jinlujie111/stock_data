@echo off
REM Master runner: repo root = %~dp0
REM 执行 main.py 来运行所有数据处理任务
REM ASCII-only REM lines (cmd.exe may mangle UTF-8).
REM MySQL: industry_indicator/config.py
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

echo.
echo ========== 执行 run_main_python.py (所有数据处理任务) ==========
python run_main_python.py
if errorlevel 1 (
  echo ERROR: 数据处理任务执行失败.
  exit /b 1
)

echo.
echo All batch jobs finished OK.

REM Optional: start HTTP API in a NEW window. Uncomment (path must not need extra quotes):
REM start "api_industry_fund_flow" cmd /k "cd /d %~dp0industry_indicator && python api_industry_fund_flow.py"

endlocal
exit /b 0

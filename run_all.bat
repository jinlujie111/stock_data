@echo off
REM Master runner: entry-point Python jobs under industry_indicator.
REM ASCII-only REM lines (cmd.exe may mangle UTF-8).
REM MySQL: industry_indicator/config.py
setlocal
cd /d "%~dp0industry_indicator"

echo.
echo ========== [1/4] run_industry_fund_flow.py ==========
python run_industry_fund_flow.py
if errorlevel 1 (
  echo ERROR: fund flow step failed.
  exit /b 1
)

echo.
echo ========== [2/4] run_industry_valuation.py --all-levels ==========
python run_industry_valuation.py --all-levels
if errorlevel 1 (
  echo ERROR: valuation step failed.
  exit /b 1
)

echo.
echo ========== [3/4] run_industry_financial_data.py (SW3 cons snapshot) ==========
python run_industry_financial_data.py
if errorlevel 1 (
  echo ERROR: industry financial data step failed.
  exit /b 1
)

echo.
echo ========== [4/4] run_industry_financial_indicator.py (full, AkShare, may take long) ==========
python run_industry_financial_indicator.py
if errorlevel 1 (
  echo ERROR: financial indicator step failed.
  exit /b 1
)

echo.
echo All batch jobs finished OK.

REM Optional: start HTTP API in a NEW window. Uncomment (path must not need extra quotes):
REM start "api_industry_fund_flow" cmd /k "cd /d %~dp0industry_indicator && python api_industry_fund_flow.py"

endlocal
exit /b 0

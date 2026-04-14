@echo off
REM Master runner: repo root = %~dp0
REM Industry jobs: industry_indicator\run_*.py
REM Stock fund flow: stock_data\run_stock_fund_flow.py (sibling package under repo root)
REM ASCII-only REM lines (cmd.exe may mangle UTF-8).
REM MySQL: industry_indicator/config.py
setlocal
set "ROOT=%~dp0"
set "IND=%ROOT%industry_indicator"
set "STOCKJOB=%ROOT%stock_data"
cd /d "%IND%"

echo.
echo ========== [1/9] run_industry_sw_universe.py (SW industry+constituents) ==========
python run_industry_sw_universe.py
if errorlevel 1 (
  echo ERROR: industry SW universe step failed.
  exit /b 1
)

echo.
echo ========== [2/9] run_industry_fund_flow.py ==========
python run_industry_fund_flow.py
if errorlevel 1 (
  echo ERROR: industry fund flow step failed.
  exit /b 1
)

echo.
echo ========== [3/9] stock_data\run_stock_fund_flow.py (per-stock THS fund flow) ==========
cd /d "%STOCKJOB%"
python run_stock_fund_flow.py
if errorlevel 1 (
  echo ERROR: stock fund flow step failed.
  exit /b 1
)
cd /d "%IND%"

echo.
echo ========== [4/9] run_industry_valuation.py --all-levels ==========
python run_industry_valuation.py --all-levels
if errorlevel 1 (
  echo ERROR: valuation step failed.
  exit /b 1
)

echo.
echo ========== [5/9] run_industry_financial_data.py (SW3 cons snapshot) ==========
python run_industry_financial_data.py
if errorlevel 1 (
  echo ERROR: industry financial data step failed.
  exit /b 1
)

echo.
echo ========== [6/9] run_industry_financial_indicator.py (full, AkShare, may take long) ==========
python run_industry_financial_indicator.py
if errorlevel 1 (
  echo ERROR: financial indicator step failed.
  exit /b 1
)

echo.
echo ========== [7/9] run_industry_order_volume.py (contract liab sum, THS, slow) ==========
python run_industry_order_volume.py
if errorlevel 1 (
  echo ERROR: industry order volume step failed.
  exit /b 1
)

echo.
echo ========== [8/9] run_industry_contract_liab_yoy.py (contract liab YoY, THS, slow) ==========
python run_industry_contract_liab_yoy.py
if errorlevel 1 (
  echo ERROR: industry contract liab yoy step failed.
  exit /b 1
)

echo.
echo ========== [9/9] run_industry_association_shipment.py (CPCA shipment YoY) ==========
python run_industry_association_shipment.py
if errorlevel 1 (
  echo ERROR: industry association shipment step failed.
  exit /b 1
)

echo.
echo ========== [10/10] run_industry_fund_flow_derivative.py (industry fund flow derivatives) ==========
python run_industry_fund_flow_derivative.py
if errorlevel 1 (
  echo ERROR: industry fund flow derivative step failed.
  exit /b 1
)

echo.
echo All batch jobs finished OK.

REM Optional: start HTTP API in a NEW window. Uncomment (path must not need extra quotes):
REM start "api_industry_fund_flow" cmd /k "cd /d %~dp0industry_indicator && python api_industry_fund_flow.py"

endlocal
exit /b 0

@echo off
chcp 65001 > nul
REM 계측 사전 지정 부하 모니터 - exe 빌드 (--onedir)
REM config.ini 는 묶지 않는다. dist 폴더의 exe 옆에 두고 쓴다.

rmdir /s /q build  2>nul
rmdir /s /q dist   2>nul

pyinstaller run_app.py ^
  --name precheck_monitor ^
  --onedir ^
  --noconfirm ^
  --collect-all streamlit ^
  --copy-metadata streamlit ^
  --collect-all plotly ^
  --collect-all bigdataquery ^
  --hidden-import openpyxl ^
  --hidden-import pymysql ^
  --add-data "app.py;." ^
  --add-data "data_source.py;." ^
  --add-data "capa_config.py;." ^
  --add-data ".streamlit;.streamlit"

if errorlevel 1 (
  echo [FAIL] 빌드 실패
  exit /b 1
)

copy /y config.ini.sample dist\precheck_monitor\config.ini > nul
echo.
echo [OK] dist\precheck_monitor\precheck_monitor.exe
echo      config.ini 의 DB 접속 정보를 채운 뒤 실행하세요.

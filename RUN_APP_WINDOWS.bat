@echo off
setlocal
cd /d "%~dp0"
set PYTHONASYNCIODEBUG=0
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
pause
endlocal

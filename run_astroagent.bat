@echo off
cd /d "%~dp0"
echo Installing AstroAgent requirements...
py -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed. Check Python and internet connection.
  pause
  exit /b 1
)
echo.
echo Running automated tests...
py -m unittest discover -s tests -v
if errorlevel 1 (
  echo One or more tests failed. Review the output above.
  pause
  exit /b 1
)
echo.
echo Running astronomy research agent...
py astro_agent.py --limit 50 --snr 5 --max-wait 120
if errorlevel 1 (
  echo The live research run did not complete. Review the error above.
  pause
  exit /b 1
)
echo.
echo Starting dashboard...
py -m streamlit run dashboard.py
pause

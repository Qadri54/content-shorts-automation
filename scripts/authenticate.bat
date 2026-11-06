@echo off
echo ======================================================================
echo YouTube Authentication Helper
echo ======================================================================
echo.
echo Langkah-langkah:
echo 1. Script akan generate URL
echo 2. Copy URL dan buka di browser
echo 3. Login dan klik Allow
echo 4. Copy authorization code dari browser
echo 5. Paste code di sini
echo.
pause

cd /d "%~dp0.."
call .venv\Scripts\activate.bat
python scripts\setup_youtube_manual.py

echo.
echo ======================================================================
if %ERRORLEVEL% EQU 0 (
    echo SUCCESS! Authentication complete.
    echo You can now run: python main.py --upload
) else (
    echo FAILED. Check error message above.
)
echo ======================================================================
pause

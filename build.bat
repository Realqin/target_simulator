@echo off
chcp 65001 > nul

echo [INFO] Activating virtual environment...
call .\.venv\Scripts\activate.bat

echo [INFO] Installing dependencies from requirements.txt...
pip install -r requirements.txt

echo [INFO] Cleaning up previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [INFO] Building the FINAL executable (windowed)...
pyinstaller --name SimuKafkaSender ^
    --onefile ^
    --windowed ^
    --clean ^
    --add-data "checkmark.svg;." ^
    --hidden-import "PyQt5.sip" ^
    main.py

echo [INFO] Building the DEBUG executable (with console)...
pyinstaller --name SimuKafkaSender_debug ^
    --onefile ^
    --clean ^
    --add-data "checkmark.svg;." ^
    --hidden-import "PyQt5.sip" ^
    main.py

echo [INFO] Copying configuration files to dist folder...
xcopy "config.json" "dist\" /Y
xcopy "initial_target.json" "dist\" /Y
xcopy "style.qss" "dist\" /Y
xcopy "checkmark.svg" "dist\" /Y

echo [INFO] Deactivating virtual environment...
deactivate

echo [SUCCESS] Build finished.
echo The 'dist' folder now contains everything needed to run.
echo.
echo [ACTION] To find the error, please run the debug version and see the output.
echo        You can redirect the output to a log file like this:
echo.
echo   cd dist
echo   SimuKafkaSender_debug.exe > log.txt 2>&1
echo.
echo   Then, open 'log.txt' to see the error details.
echo.
pause
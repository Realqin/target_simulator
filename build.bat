@echo off
echo ==================================================
echo  Starting the PyInstaller build process (Folder Mode)...
echo ==================================================

REM Get the directory of the batch file and define the output name
set "SCRIPT_DIR=%~dp0"
set "OUTPUT_DIR_NAME=SimuKafkaSender"

echo Cleaning up previous builds...
rmdir /s /q "%SCRIPT_DIR%build"
rmdir /s /q "%SCRIPT_DIR%dist"
del /q "%SCRIPT_DIR%*.spec"

echo Running PyInstaller...

pyinstaller --name "%OUTPUT_DIR_NAME%" ^
            --onedir ^
            --windowed ^
            --add-data "config.json;." ^
            --add-data "style.qss;." ^
            --add-data "initial_target.json;." ^
            --hidden-import="PyQt5.sip" ^
            --hidden-import="sqlalchemy.dialects.mysql" ^
            main.py

echo ==================================================
echo Build process finished.
echo ==================================================

REM Check if the build was successful before creating the data_track folder
if exist "%SCRIPT_DIR%dist\%OUTPUT_DIR_NAME%\%OUTPUT_DIR_NAME%.exe" (
    echo.
    echo Creating 'data_track' directory...
    mkdir "%SCRIPT_DIR%dist\%OUTPUT_DIR_NAME%\data_track"
    
    echo.
    echo Success! The application folder can be found in:
    echo %SCRIPT_DIR%dist\%OUTPUT_DIR_NAME%
    echo.
    echo You can now edit 'config.json' inside that folder directly.
    echo.
) else (
    echo.
    echo Error: Build failed. Please check the output above for errors.
    echo.
)

pause
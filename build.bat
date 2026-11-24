@echo off
rem 重新打包免安裝執行檔（產出：dist\archive_txt_tool.exe）
setlocal
cd /d "%~dp0"

python -m pip install -r requirements.txt || goto :fail
python -m PyInstaller --noconfirm --clean --onefile --windowed --name archive_txt_tool archive_txt_tool.py || goto :fail

echo.
echo 完成：%cd%\dist\archive_txt_tool.exe
pause
exit /b 0

:fail
echo.
echo 打包失敗，請查看上方訊息。
pause
exit /b 1

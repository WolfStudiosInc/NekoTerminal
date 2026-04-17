@echo off
title Neko Terminal - Decrypt Data
echo.
echo  ================================================
echo   Neko Terminal - Decrypt Encrypted Data Files
echo  ================================================
echo.
echo  This will decrypt your config, history, and AI
echo  chat files into a "decrypted" folder using your
echo  .neko_key file.
echo.
pause
python "%~dp0neko_decrypt.py"

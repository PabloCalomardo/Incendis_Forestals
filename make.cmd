@echo off
setlocal

if "%~1"=="" (
  npm run dev
  exit /b %ERRORLEVEL%
)

if "%~1"=="install" (
  npm run install:all
  exit /b %ERRORLEVEL%
)

npm run %*

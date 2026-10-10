@echo off
REM Respaldo diario de la base de produccion, con prueba de restauracion.
REM Lo dispara el Programador de tareas de Windows (ver 00_Gestion).
REM
REM Diario y no semanal por dos razones: un respaldo semanal puede perder hasta
REM siete dias de trabajo, y el plan gratuito de Supabase pausa el proyecto tras
REM una semana sin actividad, asi que una tarea semanal queda justo en el borde.
REM Cada archivo pesa unos 450 KB.

cd /d "%~dp0backend"
set PYTHONPATH=.
set PYTHONIOENCODING=utf-8

"%~dp0.venv\Scripts\python.exe" -X utf8 -m app.respaldo crear >> "%~dp0..\99_Respaldos\respaldo.log" 2>&1
if errorlevel 1 (
  echo [%DATE% %TIME%] FALLO EL RESPALDO >> "%~dp0..\99_Respaldos\respaldo.log"
  exit /b 1
)
exit /b 0

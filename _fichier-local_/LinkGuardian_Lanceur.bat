@echo off
:: Vérifie si le script est exécuté en mode administrateur
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ⚠️  Ce script doit être exécuté en tant qu'administrateur.
    echo.
    echo Relance automatique avec les droits admin...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

@echo off
REM ============================================
REM 🚀 LinkGuardian - Lanceur Automatique (RabbitMQ)
REM ============================================

title LinkGuardian - Lanceur (RabbitMQ)
color 0a

REM ============================================
REM 🧹 PURGE AVANT LE MENU (OPTIONNELLE)
REM ============================================
set RABBIT_PATH="C:\Program Files\RabbitMQ Server\rabbitmq_server-4.2.0\sbin"

echo.
echo ================================================
echo     🧹 OPTION DE PURGE RABBITMQ AU DEMARRAGE
echo ================================================
echo.
echo Souhaitez-vous purger les files RabbitMQ avant de démarrer ?
echo (Cela efface toutes les tâches Celery en attente.)
set /p purge_confirm="Votre choix (O/N) : "

if /i "%purge_confirm%"=="O" (
    echo 🧹 Purge de RabbitMQ...
    "%RABBIT_PATH%\rabbitmqctl.bat" stop_app >nul 2>&1
    "%RABBIT_PATH%\rabbitmqctl.bat" reset >nul 2>&1
    "%RABBIT_PATH%\rabbitmqctl.bat" start_app >nul 2>&1
    echo ✅ Purge effectuée avec succès.
    timeout /t 2 >nul
) else (
    echo ⏭️  Purge ignorée.
    timeout /t 1 >nul
)


:MENU
cls
echo.
echo ================================================
echo        LINKGUARDIAN - LANCEUR AUTOMATIQUE
echo ================================================
echo.
echo   [1] Démarrer LinkGuardian
echo   [2] Arrêter LinkGuardian
echo   [3] Purger RabbitMQ (files / tasks)
echo   [4] Diagnostic
echo   [5] Quitter
echo.
set /p choice="Votre choix (1-5) : "

if "%choice%"=="1" goto START
if "%choice%"=="2" goto STOP
if "%choice%"=="3" goto PURGE
if "%choice%"=="4" goto DIAGNOSTIC
if "%choice%"=="5" exit
goto MENU

REM ============================================
REM 🚀 DÉMARRAGE
REM ============================================
:START
cls
echo.
echo ================================================
echo        🚀 DEMARRAGE DE LINKGUARDIAN
echo ================================================
echo.

SET PROJECT_PATH=%~dp0
SET CONDA_ENV=linkguardian
SET RABBIT_PATH="C:\Program Files\RabbitMQ Server\rabbitmq_server-4.2.0\sbin"

echo [1/4] Vérification de RabbitMQ...
net start RabbitMQ >nul 2>&1
if %errorlevel%==0 (
    echo ✅ RabbitMQ est en cours d'exécution.
) else (
    echo ⚠️  RabbitMQ non démarré, tentative de lancement...
    net start RabbitMQ
)
timeout /t 2 >nul

echo.
echo [2/4] Démarrage du Worker Celery...
start "Celery Worker" cmd /k "cd /d %PROJECT_PATH% && call conda activate %CONDA_ENV% && celery -A celery_app.celery worker --pool=solo -l info"
timeout /t 2 >nul

echo.
echo [3/4] Démarrage de Celery Beat...
start "Celery Beat" cmd /k "cd /d %PROJECT_PATH% && call conda activate %CONDA_ENV% && celery -A celery_app.celery beat -l info"
timeout /t 2 >nul

echo.
echo [4/4] Démarrage du serveur Flask...
start "Flask Server" cmd /k "cd /d %PROJECT_PATH% && call conda activate %CONDA_ENV% && python app.py"
timeout /t 3 >nul

echo.
echo ================================================
echo   ✅ LinkGuardian est prêt !
echo   🌐 http://localhost:5000
echo ================================================
echo.
start http://localhost:5000
pause
goto MENU

REM ============================================
REM 🛑 ARRÊT
REM ============================================
:STOP
cls
echo.
echo ================================================
echo        🛑 ARRÊT DE LINKGUARDIAN
echo ================================================
echo.

taskkill /FI "WINDOWTITLE eq Celery Worker" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Celery Beat" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Flask Server" /F >nul 2>&1
net stop RabbitMQ >nul 2>&1

echo ✅ Tous les services ont été arrêtés.
pause
goto MENU

REM ============================================
REM 🧪 DIAGNOSTIC
REM ============================================
:DIAGNOSTIC
cls
echo.
echo ================================================
echo        🔍 DIAGNOSTIC LINKGUARDIAN
echo ================================================
echo.

SET CONDA_ENV=linkguardian
SET RABBIT_PATH="C:\Program Files\RabbitMQ Server\rabbitmq_server-4.2.0\sbin"
SET ALL_OK=1

echo [1/4] Vérification de RabbitMQ...
if exist %RABBIT_PATH%\rabbitmqctl.bat (
    echo ✅ RabbitMQ détecté dans : %RABBIT_PATH%
) else (
    echo ❌ RabbitMQ introuvable à cet emplacement.
    SET ALL_OK=0
)

echo.
echo [2/4] Vérification de Conda...
where conda >nul 2>&1
if %errorlevel%==0 (
    echo ✅ Conda installé
    conda env list | findstr /C:"%CONDA_ENV%" >nul 2>&1
    if %errorlevel%==0 (
        echo ✅ Environnement '%CONDA_ENV%' trouvé
    ) else (
        echo ❌ Environnement '%CONDA_ENV%' manquant
        SET ALL_OK=0
    )
) else (
    echo ❌ Conda non installé
    SET ALL_OK=0
)

echo.
echo [3/4] Vérification du projet...
if exist "%~dp0app.py" (
    echo ✅ app.py trouvé
) else (
    echo ❌ app.py manquant
    SET ALL_OK=0
)
if exist "%~dp0celery_app.py" (
    echo ✅ celery_app.py trouvé
) else (
    echo ❌ celery_app.py manquant
    SET ALL_OK=0
)

echo.
echo [4/4] Test Python...
call conda activate %CONDA_ENV% >nul 2>&1
python -c "import flask, celery" 2>nul
if %errorlevel%==0 (
    echo ✅ Dépendances OK
) else (
    echo ❌ Erreur d'import Python
    SET ALL_OK=0
)

echo.
if %ALL_OK%==1 (
    echo ================================================
    echo    ✅ TOUT EST CORRECT !
    echo ================================================
) else (
    echo ================================================
    echo    ⚠️  Problèmes détectés.
    echo ================================================
)
echo.
pause
goto MENU

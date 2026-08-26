@echo off
rem Abre a janela do Registro de Atividades da SED.
rem Basta dar dois cliques neste arquivo.
rem
rem Usa a propria pasta onde este arquivo esta (%~dp0), em vez de um
rem caminho fixo: assim funciona mesmo se a pasta for parar em outro
rem lugar que nao a Area de Trabalho.

cd /d "%~dp0"

if not exist "app.py" (
    echo Nao encontrei os arquivos do programa nesta pasta.
    echo Deixe este atalho dentro da pasta  sed_autofill.
    echo.
    pause
    exit /b 1
)

rem ------------------------------------------------------------
rem Procura o Python. As versoes com "w" no fim (pythonw / pyw)
rem abrem o programa SEM a janela preta do terminal atras.
rem
rem O "pyw" vem junto com o instalador oficial e funciona mesmo
rem quando a caixinha "Add Python to PATH" nao foi marcada na
rem instalacao - por isso ele entra na busca logo depois do
rem pythonw, antes de cair para as versoes com terminal.
rem ------------------------------------------------------------
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" pythonw app.py
    exit /b 0
)

where pyw >nul 2>&1
if not errorlevel 1 (
    start "" pyw app.py
    exit /b 0
)

where python >nul 2>&1
if not errorlevel 1 (
    start "" python app.py
    exit /b 0
)

where py >nul 2>&1
if not errorlevel 1 (
    start "" py app.py
    exit /b 0
)

echo Nao encontrei o Python neste computador.
echo.
echo Rode primeiro o arquivo  INSTALAR.bat  desta pasta.
echo.
pause
exit /b 1

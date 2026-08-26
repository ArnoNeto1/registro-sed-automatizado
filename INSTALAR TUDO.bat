@echo off
setlocal enabledelayedexpansion
title Instalacao completa - Registro SED Automatizado
cd /d "%~dp0"

echo ============================================================
echo    REGISTRO SED AUTOMATIZADO
echo    Instalacao completa (inclusive o Python)
echo ============================================================
echo.
echo  Este instalador baixa e configura tudo o que o programa
echo  precisa. Deixe o computador conectado a internet e nao
echo  feche esta janela ate aparecer "PRONTO".
echo.
echo  Pode levar de 5 a 15 minutos, dependendo da internet.
echo.
pause
echo.

rem ============================================================
rem  ETAPA 1 - Existe Python neste computador?
rem ============================================================
echo  [1/4] Procurando o Python...
call :achar_python
if defined PY (
    echo        Ja existe: !PY!
    goto tem_python
)

echo        Nao encontrei. Vou instalar o Python.
echo.

rem ------------------------------------------------------------
rem  Primeiro tentamos o winget, que e o instalador do proprio
rem  Windows: ele baixa da fonte oficial, confere a assinatura e
rem  ajusta o PATH sozinho. So se ele nao existir (Windows mais
rem  antigo) e que partimos para o download manual.
rem ------------------------------------------------------------
echo  [2/4] Instalando o Python...
where winget >nul 2>&1
if errorlevel 1 goto baixar_manual

echo        Usando o winget (instalador do Windows)...
winget install --id Python.Python.3.12 --exact --source winget ^
    --accept-package-agreements --accept-source-agreements --silent
call :achar_python
if defined PY goto tem_python

echo        O winget nao resolveu. Tentando baixar direto...

:baixar_manual
rem ------------------------------------------------------------
rem  Reserva: baixa o instalador oficial do python.org.
rem  O endereco aponta para uma versao fixa; se um dia sair do ar,
rem  o script avisa e manda instalar a mao, em vez de falhar em
rem  silencio.
rem ------------------------------------------------------------
set "PY_URL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
set "PY_EXE=%TEMP%\python-instalador-sed.exe"

echo        Baixando o instalador do Python (uns 25 MB)...
if exist "%PY_EXE%" del "%PY_EXE%" >nul 2>&1

where curl >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_EXE%' -UseBasicParsing } catch { exit 1 }"
) else (
    curl -L --fail --silent --show-error -o "%PY_EXE%" "%PY_URL%"
)

rem confere se o arquivo veio inteiro (um instalador tem dezenas de MB;
rem se vier so alguns KB, foi pagina de erro em vez do programa)
set "TAM=0"
if exist "%PY_EXE%" for %%A in ("%PY_EXE%") do set "TAM=%%~zA"
if !TAM! LSS 10000000 goto falhou_download

echo        Instalando (a janela pode parecer parada, e normal)...
start /wait "" "%PY_EXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
del "%PY_EXE%" >nul 2>&1

call :achar_python
if not defined PY goto falhou_python

:tem_python
echo.
echo  [3/4] Instalando as bibliotecas do programa...
"!PY!" -m pip install --upgrade pip
"!PY!" -m pip install -r requirements.txt
if errorlevel 1 goto falhou_libs

echo.
echo  [4/4] Baixando o navegador que o programa controla.
echo        Esta e a parte mais demorada. Aguarde.
"!PY!" -m playwright install chromium
if errorlevel 1 goto falhou_libs

rem ------------------------------------------------------------
rem  Cria o .env a partir do modelo, se ainda nao existir. Nunca
rem  sobrescreve um .env ja preenchido - seria apagar a senha e a
rem  configuracao de quem ja usa o programa.
rem ------------------------------------------------------------
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo.
        echo  Criei o arquivo .env a partir do modelo.
    )
)

echo.
echo ============================================================
echo    PRONTO! Esta tudo instalado.
echo ============================================================
echo.
echo    Falta so colocar os SEUS dados:
echo.
echo    1. Abra o arquivo  .env  desta pasta com o Bloco de Notas
echo    2. Preencha CPF, senha, seu nome, regional e escola
echo       (o arquivo "ESCOLAS - CRE BLUMENAU.txt" tem os nomes
echo        exatos das escolas para copiar)
echo    3. Salve e de dois cliques em  "Registro SED.bat"
echo.
echo    Quer abrir o .env agora? Feche o Bloco de Notas quando
echo    terminar de preencher.
echo.
choice /c SN /n /m "Abrir o .env agora? (S/N): "
if errorlevel 2 goto fim
if exist ".env" start "" notepad ".env"

:fim
echo.
pause
exit /b 0


rem ============================================================
rem  Procura o Python. Alem do PATH, olha nas pastas onde o
rem  instalador costuma colocar - necessario porque, logo depois
rem  de instalar, esta janela ainda nao enxerga o PATH novo.
rem ============================================================
:achar_python
set "PY="
where py >nul 2>&1
if not errorlevel 1 set "PY=py"
if defined PY exit /b 0
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" set "PY=%%D\python.exe"
)
if defined PY exit /b 0
for /d %%D in ("%ProgramFiles%\Python3*") do (
    if exist "%%D\python.exe" set "PY=%%D\python.exe"
)
exit /b 0


:falhou_download
echo.
echo ============================================================
echo    NAO CONSEGUI BAIXAR O PYTHON
echo ============================================================
echo.
echo    Pode ser internet instavel, bloqueio da rede da escola,
echo    ou o endereco de download ter mudado.
echo.
echo    Instale a mao, e depois rode este arquivo de novo:
echo        https://www.python.org/downloads/
echo    Na primeira tela, marque "Add Python to PATH".
echo.
pause
exit /b 1

:falhou_python
echo.
echo ============================================================
echo    O PYTHON FOI INSTALADO MAS NAO FOI ENCONTRADO
echo ============================================================
echo.
echo    Isso costuma resolver sozinho: FECHE esta janela,
echo    abra o "INSTALAR TUDO.bat" de novo e ele deve achar.
echo.
echo    Se continuar, reinicie o computador e tente mais uma vez.
echo.
pause
exit /b 1

:falhou_libs
echo.
echo ============================================================
echo    DEU ERRO AO INSTALAR AS BIBLIOTECAS
echo ============================================================
echo.
echo    Anote (ou tire foto) das mensagens em vermelho acima.
echo    Quase sempre e internet: tente de novo em outra rede.
echo.
pause
exit /b 1

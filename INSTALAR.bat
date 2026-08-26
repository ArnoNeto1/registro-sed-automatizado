@echo off
title Instalador - Registro SED Automatizado
cd /d "%~dp0"

echo ============================================================
echo    REGISTRO SED AUTOMATIZADO - instalacao
echo ============================================================
echo.

rem ------------------------------------------------------------
rem Procura o Python de tres jeitos diferentes.
rem
rem O "py" (lancador do Python) vem junto com o instalador oficial
rem e fica numa pasta que SEMPRE esta no PATH do Windows. Ja o
rem "python" e o "pip" so funcionam se a pessoa tiver marcado a
rem caixinha "Add Python to PATH" na instalacao - que e justamente
rem o passo que quase todo mundo esquece. Por isso tentamos o "py"
rem primeiro: ele resolve o caso mais comum de erro.
rem ------------------------------------------------------------
set "PY="

where py >nul 2>&1
if not errorlevel 1 set "PY=py"
if defined PY goto encontrou

where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto encontrou

where python3 >nul 2>&1
if not errorlevel 1 set "PY=python3"
if defined PY goto encontrou

echo  NAO ENCONTREI O PYTHON NESTE COMPUTADOR.
echo.
echo  Instale primeiro, neste endereco:
echo      https://www.python.org/downloads/
echo.
echo  MUITO IMPORTANTE: na PRIMEIRA tela do instalador, marque a
echo  caixinha "Add Python to PATH" (fica embaixo, e pequena)
echo  antes de clicar em "Install Now".
echo.
echo  Depois de instalar, rode este arquivo de novo.
echo.
pause
exit /b 1

:encontrou
echo  Python encontrado.
%PY% --version
echo.
echo  ----------------------------------------------------------
echo  [1 de 2] Instalando as bibliotecas do programa...
echo  ----------------------------------------------------------
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto falhou

echo.
echo  ----------------------------------------------------------
echo  [2 de 2] Instalando o navegador que o programa controla.
echo           Esta e a parte mais demorada - pode levar alguns
echo           minutos. Nao feche esta janela.
echo  ----------------------------------------------------------
%PY% -m playwright install chromium
if errorlevel 1 goto falhou

echo.
echo ============================================================
echo    PRONTO! Instalacao concluida.
echo ============================================================
echo.
echo    Ainda falta colocar os seus dados:
echo.
echo    1. Nesta pasta, copie o arquivo  .env.example
echo       e renomeie a copia para apenas  .env
echo    2. Abra esse .env no Bloco de Notas e preencha seu CPF,
echo       senha, nome, regional e escola.
echo    3. De dois cliques em  "Registro SED.bat"  para abrir.
echo.
pause
exit /b 0

:falhou
echo.
echo ============================================================
echo    DEU ERRO NA INSTALACAO
echo ============================================================
echo.
echo    Anote (ou tire foto) das mensagens em vermelho acima e
echo    peca ajuda. Elas dizem exatamente o que faltou.
echo.
pause
exit /b 1

; ---------------------------------------------------------------------
; Instalador do Registro SED Automatizado (Inno Setup)
; https://jrsoftware.org/isinfo.php
;
; Compilado automaticamente pelo GitHub Actions
; (.github/workflows/montar-programa.yml), que chama o ISCC assim:
;
;   ISCC /DMyAppVersion=1.4.2 installer\setup.iss
;
; e espera encontrar, relativos a esta pasta (installer\):
;   ..\dist\Registro-SED.exe        (gerado pelo PyInstaller)
;   ..\assets\icone.ico             (ícone do programa)
;
; Para testar na sua máquina Windows sem o Actions: instale o Inno
; Setup, gere o .exe com o comando do PyInstaller que está no workflow
; (adicionando --icon assets\icone.ico) e depois clique com o botão
; direito neste arquivo > "Compile".
; ---------------------------------------------------------------------

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "Registro SED Automatizado"
#define MyAppPublisher "Arno Neto"
#define MyAppExeName "Registro-SED.exe"
#define MyAppIcon "..\assets\icone.ico"
#define MyAppURL "https://github.com/ArnoNeto1/registro-sed-automatizado"

[Setup]
; Identificador fixo do programa (gerado uma única vez). Não mude: é o
; que faz o Windows entender que uma nova versão é uma ATUALIZAÇÃO do
; mesmo programa, e não uma instalação nova ao lado da antiga.
AppId={{5B6A8C2E-6C1F-4B3A-9E77-3F0B4D5C7A21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Instala para todos os usuários da máquina, em "Arquivos de Programas".
; Por isso pede permissão de administrador ao abrir o instalador.
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist_instalador
OutputBaseFilename=Registro-SED-Instalador
SetupIconFile={#MyAppIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: checkedonce

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\.env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\ESCOLAS - CRE BLUMENAU.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\VERSAO.txt"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Desde a versão 1.5, o .env (CPF/senha), o login salvo do navegador
; (browser_profile\) e o histórico de envios NÃO ficam mais aqui — foram
; para %ProgramData%\RegistroSED, pasta compartilhada por TODOS os
; usuários do Windows na máquina (ver caminhos.pasta_de_dados() no
; código — tem que ser por MÁQUINA, não por usuário do Windows: dois
; professores que dividem o laboratório precisam ver o mesmo histórico
; de envios, senão um reenviaria o que o outro já registrou). Criada
; aqui, já com permissão de escrita, para não depender de o programa
; conseguir criá-la sozinho na primeira execução.
Name: "{commonappdata}\RegistroSED"; Permissions: users-modify

; Mesmo com os dados do professor fora daqui, a autoatualização
; (atualizador.py) ainda troca o próprio Registro-SED.exe e reescreve o
; VERSAO.txt NESTA pasta, dentro de "Arquivos de Programas" — protegida
; por padrão contra escrita por usuários comuns. Por isso a permissão
; continua liberada: sem ela, um professor sem privilégio de
; administrador não conseguiria se autoatualizar.
Name: "{app}"; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o {#MyAppName} agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Ao desinstalar, remove também os arquivos que o programa criou depois
; (histórico, config, login salvo, .env com CPF/senha) — sem isso
; ficariam órfãos na máquina.
;
; Desde a 1.5 esses dados moram em %ProgramData%\RegistroSED (fora de
; "{app}"); os itens abaixo em "{app}" continuam aqui só para limpar uma
; instalação de versão anterior à 1.5 que seja desinstalada antes de
; nunca ter sido aberta com o instalador novo (ou seja, antes de rodar a
; migração automática) — não fazem mal nenhum ficar mesmo quando não há
; nada ali para apagar.
Type: filesandordirs; Name: "{app}\browser_profile"
Type: files; Name: "{app}\.env"
Type: files; Name: "{app}\registros_enviados.json"
Type: files; Name: "{app}\configuracao.json"
Type: files; Name: "{app}\aulas_nao_realizadas.json"
Type: files; Name: "{app}\ultimo_professor.txt"
Type: files; Name: "{app}\erro.txt"
Type: filesandordirs; Name: "{commonappdata}\RegistroSED"

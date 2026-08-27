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
; O programa guarda o .env (CPF/senha), o login salvo do navegador
; (browser_profile\) e o histórico de envios do LADO do próprio
; executável. Como a pasta de instalação fica dentro de "Arquivos de
; Programas" — protegida por padrão contra escrita por usuários comuns
; — liberamos aqui a permissão de escrita para o grupo "Usuários"
; nesta pasta específica. Sem isso, o programa abriria e falharia ao
; tentar criar o .env na primeira execução.
Name: "{app}"; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o {#MyAppName} agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Ao desinstalar, remove também os arquivos que o programa criou depois
; (histórico, config, login salvo) — sem isso ficariam órfãos na pasta.
Type: filesandordirs; Name: "{app}\browser_profile"
Type: files; Name: "{app}\.env"
Type: files; Name: "{app}\registros_enviados.json"
Type: files; Name: "{app}\configuracao.json"
Type: files; Name: "{app}\aulas_nao_realizadas.json"
Type: files; Name: "{app}\ultimo_professor.txt"
Type: files; Name: "{app}\erro.txt"

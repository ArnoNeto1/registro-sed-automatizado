# Registro SED Automatizado

Programa para professores orientadores de tecnologia (Blumenau/SC) que lê a
agenda de reservas do laboratório do NTE Blumenau e preenche sozinho o
formulário da SED-SC de "Registro de Atividades dos Professores Orientadores
de Tecnologias Educacionais ou Maker" — parando sempre antes de enviar, para
você conferir.

**Ele nunca envia nada sem você clicar em "Enviar para a SED".**

## Para professores — baixar e instalar

Não precisa instalar Python nem nada: baixe pela página de
[**Releases**](https://github.com/ArnoNeto1/registro-sed-automatizado/releases/latest).
Duas opções, faça o que for mais fácil para você:

- **`Registro-SED.exe`** (portátil) — baixe, coloque numa pasta própria (ex.:
  `Área de Trabalho\Registro SED`) e dê dois cliques. Ele mesmo cria, ao
  lado, o que precisa na primeira vez.
- **`Registro-SED-Instalador.exe`** — instala de verdade, com atalho no Menu
  Iniciar e na Área de Trabalho, e aparece em "Adicionar ou remover
  programas" do Windows. Pede senha de administrador uma vez, na instalação.

As duas formas se atualizam sozinhas quando sai versão nova, e leem/escrevem
a mesma coisa (login salvo, histórico de envios) — pode trocar de uma para a
outra sem perder nada.

Depois de instalado, o arquivo **`COMECE AQUI.txt`** (vem junto) explica o
passo a passo — cadastro na primeira tela, como dividir o computador com
outro professor do laboratório, perguntas frequentes.

## Como funciona (resumo)

1. Loga no site de agendamento (nteblumenau.com.br) com CPF e senha.
2. Lê a semana atual e agrupa aulas emendadas da mesma turma/disciplina numa
   única atividade, contando quantas "aulas de 45min" foram usadas.
3. Identifica pelo horário qual aula está acontecendo agora (ou acabou de
   acontecer) e já deixa ela sugerida — só falta dizer quantos estudantes
   foram atendidos, a única informação que não existe na agenda.
4. Preenche o formulário da SED em segundo plano, página por página, e
   **confere cada resposta lida de volta da própria página** — não é uma
   promessa do que o programa pretendia escrever, é o que está lá de fato.
5. Mostra o resumo e para. Só envia depois que você clicar em "Enviar para a
   SED" e confirmar.

O histórico do que já foi enviado é do **computador** (ou da instalação),
não da pessoa — de propósito: dois professores que dividem o mesmo
laboratório, em turnos diferentes, precisam ver a mesma agenda e o mesmo
histórico, senão um acabaria reenviando o que o outro já registrou.

## Limitações conhecidas

- **Só cobre o fluxo "Atividade/Aula com estudantes".** Os outros tipos de
  registro do formulário (Suporte a outros espaços, Manutenção de
  equipamentos, Formação/Reunião) ainda não foram mapeados — o programa
  ignora automaticamente os agendamentos de "Organização interna na Sala de
  Tecnologias/Formação".
- **Número de estudantes** continua manual porque o site de agendamento não
  guarda essa informação.
- **Layout do site do NTE pode mudar.** Os seletores usados em
  `agenda_scraper.py` foram tirados do HTML real em 20/08/2026.
- **Layout do formulário da SED também pode mudar** (novas perguntas, novos
  componentes curriculares). O mapeamento em
  `config.DISCIPLINA_PARA_COMPONENTE` foi conferido em 24/08/2026 direto na
  estrutura interna do formulário.

## Para quem for mexer no código

### Rodando a partir do código-fonte

```bash
git clone https://github.com/ArnoNeto1/registro-sed-automatizado.git
cd registro-sed-automatizado
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium   # só usado se não achar Chrome/Edge na máquina

cp .env.example .env
# ou: python app.py e cadastre pela tela (recomendado — .env é o formato antigo)
```

- **`python app.py`** — a interface gráfica (janela), o jeito normal de usar.
- **`python main.py --dry-run`** — linha de comando, só para conferir o que
  seria enviado sem preencher nada. Veja `python main.py --help` para as
  opções (`--semana`, `--turnos`, `--professor`, `--auto-submit` etc.).

### Estrutura dos arquivos

| Arquivo | O que é |
|---|---|
| `app.py` | Interface gráfica (Tkinter) — o programa do dia a dia. |
| `main.py` | Script de linha de comando (mesma automação, sem janela). |
| `iniciar.py` | Porta de entrada do `.exe` — rede de segurança contra falha antes da tela existir (gera `erro.txt`). |
| `agenda_scraper.py` | Login e leitura do site de agendamento do NTE. |
| `sed_form_filler.py` | Preenchimento do formulário da SED, página por página, com conferência de cada resposta. |
| `config.py` | Dados fixos e mapeamentos (disciplina → componente curricular etc.). |
| `configuracao.py` | Tela de cadastro (nome, escola, CPF, turnos) — substitui a edição manual do `.env`. |
| `caminhos.py` | Onde ficam os arquivos do programa (`.py` vs `.exe`, portátil vs instalado) e qual navegador usar. |
| `atualizador.py` | Autoatualização: consulta `versao.json`, baixa e troca os arquivos/o `.exe`. |
| `escolas.py` | Lista de escolas da CRE Blumenau, como aparecem no formulário da SED. |
| `installer/setup.iss` | Script do instalador Windows (Inno Setup). |
| `.github/workflows/montar-programa.yml` | Gera o `.exe` portátil e o instalador e publica a release, automaticamente. |

### Onde ficam os dados do professor

`.env` (ou a configuração feita pela tela), o login salvo do navegador
(`browser_profile/`) e o histórico de envios ficam:

- **ao lado do executável**, rodando pelos `.py` ou pelo `.exe` portátil;
- em **`%ProgramData%\RegistroSED`**, quando instalado dentro de "Arquivos
  de Programas" (o instalador) — pasta compartilhada por todos os usuários
  do Windows na máquina, não por usuário, para não quebrar o
  compartilhamento entre professores descrito acima. Ver
  `caminhos.pasta_de_dados()`.

### Publicando uma versão nova

Aumente o número em `VERSAO.txt`, descreva o que mudou numa seção nova em
`NOVIDADES.md` e dê push na `main` — o GitHub Actions
(`.github/workflows/montar-programa.yml`) monta o `.exe` portátil e o
instalador, publica os dois numa Release e atualiza `versao.json`, que é o
que os programas já instalados consultam para saber que existe versão nova.
Veja `PUBLICAR ATUALIZACAO.txt` para o passo a passo completo.

## Licença

[MIT](LICENSE).

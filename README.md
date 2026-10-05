# Registro SED Automatizado

[![Versão mais recente](https://img.shields.io/github/v/release/ArnoNeto1/registro-sed-automatizado?label=vers%C3%A3o&color=2f6f4f)](https://github.com/ArnoNeto1/registro-sed-automatizado/releases/latest)
[![Baixar o instalador](https://img.shields.io/badge/⬇%20Baixar-Instalador%20(.exe)-2f6f4f?style=for-the-badge)](https://github.com/ArnoNeto1/registro-sed-automatizado/releases/latest/download/Registro-SED-Instalador.exe)
[![Baixar a versão portátil](https://img.shields.io/badge/⬇%20Baixar-Vers%C3%A3o%20port%C3%A1til-6b7684?style=for-the-badge)](https://github.com/ArnoNeto1/registro-sed-automatizado/releases/latest/download/Registro-SED.exe)

> Os dois botões acima baixam sempre a versão mais nova, sem precisar
> procurar nada. Na dúvida, escolha o **Instalador**.

## Para que serve

Programa para professores orientadores de tecnologia (Blumenau/SC). Ele lê
a agenda de reservas do laboratório do NTE Blumenau e preenche sozinho o
formulário da SED-SC de "Registro de Atividades dos Professores Orientadores
de Tecnologias Educacionais ou Maker" — economizando o trabalho manual de
copiar os dados da agenda para o formulário, aula por aula.

Cobre os 4 tipos de registro que o formulário oferece: Atividade/Aula com
estudantes, Suporte a outros espaços (instalar/configurar equipamento),
Manutenção de equipamentos e Formação/Reunião — os três últimos nem
precisam de aula marcada na agenda: têm botão próprio, sempre disponível.
E se o laboratório (ou tablet/projetor) foi usado sem reserva na agenda
do NTE, também dá para registrar: é só usar o link "Registrar aula sem
agendamento" embaixo da lista de aulas.

**Ele nunca envia nada sozinho.** Sempre para antes do envio, mostra um
resumo de tudo que vai para a SED, e só manda depois que você clicar em
"Enviar para a SED" e confirmar.

## Veja funcionando

![Demonstração: baixar, cadastrar, entrar, ler a agenda e preencher o formulário](docs/demonstracao.gif)

Do download até o formulário pronto para conferir — o programa para aí e
espera você clicar em "Enviar para a SED". Nesta demonstração, os nomes dos
professores da agenda, o e-mail da escola e o campo de senha aparecem
tarjados por privacidade; no seu computador eles aparecem normalmente.

## Como instalar e usar

1. Baixe a versão mais recente na página de
   [**Releases**](https://github.com/ArnoNeto1/registro-sed-automatizado/releases/latest).
   Não precisa instalar Python nem nada — escolha um dos dois arquivos:
   - **`Registro-SED.exe`** — portátil. Coloque numa pasta própria (ex.:
     `Área de Trabalho\Registro SED`) e dê dois cliques para abrir.
   - **`Registro-SED-Instalador.exe`** — instala de verdade, com atalho no
     Menu Iniciar e na Área de Trabalho. Pede senha de administrador uma
     vez, na instalação.
2. Na primeira abertura, preencha a tela de cadastro: escola, seu nome, seu
   CPF e os turnos que você atende.
3. O programa já abre com a agenda do dia carregada e a aula mais recente
   sugerida. Escolha a aula, diga quantos estudantes foram atendidos e
   clique em **"Preencher formulário"**.
4. Confira o resumo (cada campo já é lido de volta da própria página, não é
   só uma promessa) e clique em **"Ver no navegador"** se quiser olhar o
   formulário preenchido com os próprios olhos antes de decidir.
5. Só então clique em **"Enviar para a SED"** e confirme.

Isso cobre uma aula normal de laboratório. Se o que você vai registrar é
suporte/instalação de equipamento, manutenção, ou uma formação/reunião,
use as outras abas em cima da lista de aulas — os campos do formulário se
ajustam sozinhos para o tipo escolhido.

### Objetos do conhecimento com IA (opcional)

O "Conteúdo aplicado" vem com o assunto que o professor escreveu na
agenda — muitas vezes genérico ("atividade de geografia - mercantilismo").
O botão **"Escrever com IA..."**, ao lado do campo, abre uma conversa que
transforma isso num texto de objetos do conhecimento no formato da SED
("Foram abordados conteúdos de... Também foram desenvolvidas habilidades
de..."). Dá para contar mais detalhes ou pedir correções na conversa, e o
texto só entra no campo quando você clica em **"Usar este texto"**.

Usa o Gemini (Google) por **dois caminhos**:

1. **Serviço da escola** — quando o programa vem configurado com o endereço
   dele (`SERVIDOR_IA_URL` e `SERVIDOR_IA_TOKEN`, ou um `servidor_ia.json`
   embutido na montagem), o professor não precisa de nada: é só clicar. Quem
   guarda a chave é um pequeno servidor (pasta [`servidor-ia/`](servidor-ia/),
   ver o README de lá), nunca o programa nem este repositório.
2. **Chave própria** — o professor cola uma chave criada de graça no
   [Google AI Studio](https://aistudio.google.com/apikey) (ou define
   `CHAVE_GEMINI`, no `.env` ou no Windows — de propósito não é
   `GEMINI_API_KEY`, o nome que outras ferramentas usam). Se existe chave
   própria, ela tem preferência sobre o
   serviço da escola.

Sem nenhum dos dois, o resto do programa funciona exatamente igual. O modelo
padrão é o `gemini-3.5-flash-lite`; dá para trocar com `MODELO_IA=...`.

**Privacidade:** o que você escreve na conversa e os dados da aula
(disciplina, turma, recursos, assunto da agenda) são enviados à Google
para gerar o texto. Nome de professor não vai, mas o texto livre o programa
não consegue filtrar — por isso a janela avisa para não digitar nomes de
estudantes. Texto com CPF, e-mail ou telefone é barrado antes de sair do
computador (e o servidor confere de novo). **Atenção:** numa chave
*gratuita*, a Google pode usar o conteúdo para melhorar os produtos dela e
pessoas podem lê-lo. Uma assinatura do Gemini não muda isso: só uma chave
com a conta de faturamento ligada no AI Studio (plano pago) fica de fora
desse uso. **Hoje o serviço da escola usa uma chave gratuita**, e a janela
avisa isso aos professores (`AVISO_DE_PRIVACIDADE` em `assistente_ia.py`);
ao passar para uma chave paga, ajuste esse texto e o das notas da versão.

Os dois formatos de instalação (portátil e instalador) se atualizam
sozinhos quando sai versão nova, e compartilham os mesmos dados — dá para
trocar de um para o outro sem perder nada. O arquivo
[**`COMECE AQUI.txt`**](COMECE%20AQUI.txt), aqui no repositório, tem mais
detalhes: como dividir o computador com outro professor do laboratório,
perguntas frequentes.

## Limitações conhecidas

- **Número de estudantes** continua manual — o site de agendamento não
  guarda essa informação.
- **Layout do site do NTE ou do formulário da SED pode mudar** a qualquer
  momento (novas perguntas, novos componentes curriculares), o que pode
  exigir ajuste em `agenda_scraper.py` ou `config.py`.

## Para quem for mexer no código

### Rodando a partir do código-fonte

```bash
git clone https://github.com/ArnoNeto1/registro-sed-automatizado.git
cd registro-sed-automatizado
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium   # só usado se não achar Chrome/Edge na máquina

python app.py   # abre a interface gráfica e cadastra pela tela
```

Também dá para rodar por linha de comando (`python main.py --dry-run`,
sem preencher nada de verdade) — veja `python main.py --help`.

Testes (só biblioteca padrão, sem navegador nem internet):

```bash
python -m unittest discover -s tests -v
```

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
| `atualizador.py` | Autoatualização: consulta `versao.json`, baixa, confere (tamanho e SHA-256) e troca os arquivos/o `.exe`. |
| `assistente_ia.py` | "Escrever com IA...": a janela de conversa e a escolha entre o serviço da escola e a chave própria (opcional). |
| `ia_gemini.py` | Núcleo da IA, sem tela: instrução, limpeza do texto e chamada ao Gemini. Compartilhado com o servidor. |
| `servidor-ia/` | Servidor intermediário (função da Vercel) que guarda a chave do Gemini da escola. Ver o README da pasta. |
| `escolas.py` | Lista de escolas da CRE Blumenau, como aparecem no formulário da SED. |
| `tests/` | Testes automáticos (`python -m unittest discover -s tests`). |
| `installer/setup.iss` | Script do instalador Windows (Inno Setup). |
| `.github/workflows/montar-programa.yml` | Gera o `.exe` portátil e o instalador e publica a release, automaticamente. |

Dados do professor (`.env`/cadastro, login do navegador, histórico de
envios) ficam ao lado do executável no modo portátil, ou em
`%ProgramData%\RegistroSED` quando instalado dentro de "Arquivos de
Programas" — ver `caminhos.pasta_de_dados()`.

### Publicando uma versão nova

Aumente o número em `VERSAO.txt`, descreva o que mudou numa seção nova em
`NOVIDADES.md` e dê push na `main` — o GitHub Actions monta o `.exe`
portátil e o instalador, publica os dois numa Release e atualiza
`versao.json` sozinho. Veja `PUBLICAR ATUALIZACAO.txt` para o passo a passo
completo.

## Agradecimentos

- **Guilherme Dornelles** (EEB Ivo D'Aquino, Gaspar) — na v1.9.3, o
  atualizador que confere o download antes de trocar o programa (tamanho e
  SHA-256) e a correção da reabertura automática (erro `init.tcl`), ambos
  com testes automáticos; e, na v1.10.0, a ideia e a primeira versão do
  "Escrever com IA..." (que depois ganhou o serviço da escola e o Gemini).

## Licença

[MIT](LICENSE).

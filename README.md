# Preenchimento automático do formulário da SED a partir da agenda do NTE Blumenau

Este script lê os agendamentos do laboratório (nteblumenau.com.br) e
preenche automaticamente o Google Forms "REGISTRO DE ATIVIDADES DOS
PROFESSORES ORIENTADORES DE TECNOLOGIAS EDUCACIONAIS OU MAKER" da SED-SC.

## Como funciona (resumo)

1. Loga no site de agendamento com seu CPF e senha.
2. Lê a semana pedida (Matutino/Vespertino/Noturno) e agrupa aulas emendadas
   da mesma turma/disciplina em uma única atividade, contando quantas
   "aulas de 45min" foram usadas.
3. Para cada atividade, pergunta no terminal:
   - **número de estudantes atendidos** — não existe no site de agendamento
     hoje, por isso é sempre perguntado;
   - **quais recursos do laboratório foram usados** — idem.
4. Preenche o formulário da SED no navegador, página por página.
5. **Nunca envia sozinho**: mostra um resumo e só clica em "Enviar" depois
   que você digitar `s` no terminal (a menos que use `--auto-submit`).

## Instalação

```bash
cd sed_autofill
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium

cp .env.example .env
# edite o .env com seu CPF, senha e dados do orientador
```

## Uso

```bash
# só olhar o que seria enviado, sem preencher nada (recomendado na primeira vez)
python main.py --dry-run

# ler a semana atual e preencher o formulário (pede confirmação antes de enviar
# cada aula, e antes disso pergunta se a aula realmente aconteceu)
python main.py
```

Sem `--semana`, o script já usa a semana de hoje. **Só aulas que já
começaram são processadas** — uma aula agendada para mais tarde no mesmo dia
nunca é mostrada para envio (regra de ouro: nunca adiantar aula futura). Use
`--incluir-futuras` só para conferir a agenda inteira com `--dry-run`.

O script também guarda em `registros_enviados.json` (nesta mesma pasta)
quais aulas já foram enviadas, então rodar o script de novo no mesmo dia não
oferece a mesma aula duas vezes.

Na primeira vez que o script abrir o formulário da SED, uma janela do
Chrome vai pedir o login da conta Google (a mesma que você usou para
acessar o formulário no navegador). Faça login manualmente uma vez — a
sessão fica salva em `browser_profile/` e não será pedida de novo enquanto
essa pasta não for apagada.

### Outras opções

- `--semana 2026-08-17` — processa uma semana específica em vez da atual
  (qualquer data dessa semana serve). Útil para conferir uma semana passada
  com `--dry-run`; nunca envia aula futura mesmo assim.
- `--turnos Matutino,Vespertino` — processa só os turnos informados.
- `--professor "Nome Completo"` — processa só os agendamentos desse
  professor (por padrão usa `PROFESSOR_FILTRO` do `.env`; deixe em branco
  para processar a aula de qualquer professor que usou o laboratório).
- `--perguntar-recursos` — pergunta no terminal quais recursos foram usados
  em cada aula, em vez de usar automaticamente os 3 recursos padrão
  definidos em `config.RECURSOS_PADRAO`.
- `--incluir-futuras` — só para conferência com `--dry-run`: mostra também
  aulas que ainda vão acontecer. Nunca processa nem envia essas aulas.
- `--auto-submit` — pula a confirmação manual e envia direto. Só recomendado
  depois de validar bastante o fluxo manualmente.

## O que ainda precisa de melhorias

- **Só cobre o fluxo "Atividade/Aula com estudantes".** Os outros tipos de
  registro do formulário (Suporte a outros espaços, Manutenção de
  equipamentos, Formação/Reunião) ainda não foram mapeados — hoje o script
  ignora automaticamente os agendamentos de "Organização interna na Sala de
  Tecnologias\Formação".
- **Número de estudantes** continua manual porque o site de agendamento não
  guarda essa informação — o script sempre pergunta no terminal, depois de
  confirmar que a aula realmente aconteceu.
- **Layout do site do NTE pode mudar.** Os seletores usados
  (`.weekly-cell.reserved`, `.reserva-professor` etc.) foram tirados do HTML
  real em 20/08/2026. Se o site for atualizado, os seletores em
  `agenda_scraper.py` podem precisar de ajuste.
- **Layout do formulário da SED também pode mudar** (novas perguntas, novos
  componentes curriculares). O mapeamento em `config.DISCIPLINA_PARA_COMPONENTE`
  foi conferido em 24/08/2026 direto na estrutura interna do formulário —
  inclusive o detalhe de que "Educação Digital" aparece **sem** "(ETI)" nos
  Anos Iniciais e **com** "(ETI)" nos Anos Finais (por isso esse item usa
  `ETAPA_DEPENDENTE` em vez de uma lista fixa).

## Estrutura dos arquivos

- `config.py` — todos os dados fixos e mapeamentos (edite aqui para ajustar
  regras, sem mexer no resto do código).
- `agenda_scraper.py` — login e leitura do site de agendamento.
- `sed_form_filler.py` — preenchimento do formulário da SED, página por
  página.
- `main.py` — script principal (linha de comando).

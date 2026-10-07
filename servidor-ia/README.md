# Servidor da IA do Registro SED

Pequena função da Vercel (Python, sem dependências) que guarda a chave do
Gemini da escola e escreve os textos do registro para o programa: os "objetos
do conhecimento" (laboratório) e as breves descrições de suporte, manutenção e
formação/reunião. O professor não precisa de chave nenhuma.

```
programa (.exe)  ──x-app-token──▶  servidor (esta pasta)  ──chave──▶  Gemini
dados do registro + conversa       instrução FIXA, limites            (Google)
```

A chave **só existe aqui**, numa variável de ambiente. Nunca vai para o
programa nem para o repositório (que é público).

## Testar no seu computador (antes de publicar qualquer coisa)

```bash
python servidor-ia/rodar_local.py
```

Pede a chave com a digitação escondida e atende em
`http://127.0.0.1:8787/api/ia`. Para o programa usar esse endereço, defina
`SERVIDOR_IA_URL=http://127.0.0.1:8787/api/ia` e
`SERVIDOR_IA_TOKEN=teste-local` antes de abri-lo.

## Onde está publicado

Projeto **`registro-sed-ia`** na conta pessoal da Vercel (plano Hobby),
região São Paulo (`gru1`). Endereço de produção:

    https://registro-sed-ia-plexe1.vercel.app/api/ia

A produção é pública de propósito (quem protege é o `x-app-token`); só as
prévias ficam atrás do login da Vercel. Se faltar `GEMINI_API_KEY` ou
`APP_TOKEN`, o servidor **recusa tudo** com 503 ("ainda não está
configurado").

Foi publicado enviando os arquivos de `api/` direto (sem ligar ao GitHub),
e os hashes SHA-1 conferidos contra os arquivos desta pasta. Por isso
**mudar o código aqui não atualiza o servidor sozinho**: é preciso publicar
de novo (mesmo envio de `api/ia.py`, `api/_ia_gemini.py` e `api/uso.py`), ou ligar o
projeto a este repositório com **Root Directory = `servidor-ia`**.

## Como está configurado

- **Vercel** (*Settings → Environment Variables*, tipo Secret, só
  Production): `GEMINI_API_KEY` (a chave do Gemini) e `APP_TOKEN` (segredo
  longo e aleatório). `MODELO_IA` é opcional (ver "Troca automática de
  modelo", abaixo). Variável nova só vale em deploy novo.
- **GitHub** (*Settings → Secrets and variables → Actions*):
  `SERVIDOR_IA_URL` (o endereço acima) e `SERVIDOR_IA_TOKEN` (o MESMO
  valor de `APP_TOKEN`). A montagem do `.exe` os embute num
  `servidor_ia.json`, que nunca vai para o repositório.

## Troca automática de modelo

No plano gratuito cada modelo do Gemini tem cota própria (pedidos por
minuto e por dia). O servidor tenta os modelos de `MODELOS_PADRAO`
(`ia_gemini.py`) na ordem: se o primeiro estiver no limite, sobrecarregado
ou aposentado, o seguinte atende e o professor nem percebe. Só esses três
erros trocam de modelo; chave recusada, filtro de segurança e internet fora
do ar aparecem como antes. Cada troca vai para o registro da Vercel como
`[ia] limite no modelo ... — tentando o próximo` (só o tipo do erro e o nome
do modelo, nunca o conteúdo). Com `MODELO_IA=a,b,c` no painel você define a
lista; um nome só usa esse modelo e nenhum outro. Todas as tentativas juntas
têm teto de 55 s (`TEMPO_TOTAL`), porque o programa espera 60 s pelo
servidor: um modelo sobrecarregado pode levar de 30 a 50 s para falhar, e
sem esse teto o professor veria um erro de rede em vez da mensagem do
servidor.

## Contagem de uso (`api/uso.py`)

Função separada, publicada junto: o programa (a partir da 2.1.0) manda
`POST /api/uso` com `{"id": "<32 caracteres hex>", "versao": "2.1.0"}` e o
mesmo `x-app-token` da IA, no máximo uma vez por dia por computador. O
`GET /api/uso` devolve os totais em JSON (público: só números); `python
contar_usuarios.py` mostra isso em texto.

- **Onde guarda:** num Redis gratuito da Upstash (plano Free: 500 mil
  comandos por mês, sem cartão). Para ligar: Vercel → Marketplace →
  Upstash → Redis → plano Free → ligar ao projeto `registro-sed-ia`. A
  Vercel cria sozinha `KV_REST_API_URL` e `KV_REST_API_TOKEN` (também
  valem `UPSTASH_REDIS_REST_URL` e `UPSTASH_REDIS_REST_TOKEN`). Variável
  nova só vale em deploy novo.
- **O que fica guardado:** contadores HyperLogLog (por dia, por versão e
  no total). Eles dão a quantidade de números diferentes, com ~1% de erro,
  mas não guardam os números: não dá para listá-los nem saber quem é
  quem. O código não grava o IP nem registra o número, o segredo ou o
  conteúdo; o registro só diz o motivo de uma recusa.
- **Quem fica de fora:** o computador que tem `modo_teste.txt` na pasta de
  dados (ver `PUBLICAR ATUALIZACAO.txt`).

## O que ainda recomendo

1. **Chave com faturamento ligado.** Numa chave gratuita a Google usa o
   conteúdo dos professores para melhorar os produtos dela e pessoas podem
   lê-lo (uma assinatura do Gemini não muda isso; só o faturamento ligado
   na chave). Trocar é só mudar o valor de `GEMINI_API_KEY` na Vercel e
   publicar de novo — o programa não muda.
2. **Um projeto do Google só da escola.** A cota é do PROJETO, não da
   chave: se a chave da escola dividir o projeto com outras ferramentas,
   qualquer rajada delas deixa os professores sem IA (o painel
   https://ai.dev/rate-limit mostra o uso por modelo). Crie a chave da
   escola num projeto novo no AI Studio.
3. No Google AI Studio / Cloud, um **orçamento com alerta e, se der, um
   teto de cota** no projeto da chave: é a defesa final contra abuso.
4. Girar o `APP_TOKEN` se houver suspeita de vazamento: novo valor na
   Vercel e no GitHub (`SERVIDOR_IA_TOKEN`), republicar o servidor e
   publicar uma versão nova do programa.

## Regras de defesa (ver `api/ia.py`)

- só POST com o `x-app-token` certo; a instrução é fixa e mora aqui;
- só os campos combinados do registro passam, com limite de tamanho; nunca
  nome de professor. O tipo de texto que a IA escreve vem no campo
  `finalidade`, que só vale se for um dos combinados (`objetos`, `suporte`,
  `manutencao`, `formacao`): sem ele é o laboratório (as versões até a 2.1.0
  não o mandam) e um valor desconhecido leva erro 400;
- recusa texto que pareça ter CPF, e-mail ou telefone (o programa também
  barra antes de enviar); nome de pessoa não dá para detectar, fica com o
  aviso da janela;
- erro cru da Google nunca volta; o conteúdo dos pedidos nunca é
  registrado (nem o dado pessoal achado: só o tipo vai para o registro).

## Atenção: `api/_ia_gemini.py` é cópia

É uma cópia **exata** de `ia_gemini.py` (raiz do repositório), porque esta
pasta é publicada sozinha. O teste `tests/test_servidor_ia.py` falha se
elas ficarem diferentes. Mexeu na raiz? Copie o arquivo por cima:

```bash
cp ia_gemini.py servidor-ia/api/_ia_gemini.py
```

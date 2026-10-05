# Servidor da IA do Registro SED

Pequena função da Vercel (Python, sem dependências) que guarda a chave do
Gemini da escola e escreve os "objetos do conhecimento" para o programa. O
professor não precisa de chave nenhuma.

```
programa (.exe)  ──x-app-token──▶  servidor (esta pasta)  ──chave──▶  Gemini
dados da aula + conversa           instrução FIXA, limites            (Google)
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
de novo (mesmo envio de `api/ia.py` e `api/_ia_gemini.py`), ou ligar o
projeto a este repositório com **Root Directory = `servidor-ia`**.

## Como está configurado

- **Vercel** (*Settings → Environment Variables*, tipo Secret, só
  Production): `GEMINI_API_KEY` (a chave do Gemini) e `APP_TOKEN` (segredo
  longo e aleatório). `MODELO_IA` é opcional. Variável nova só vale em
  deploy novo.
- **GitHub** (*Settings → Secrets and variables → Actions*):
  `SERVIDOR_IA_URL` (o endereço acima) e `SERVIDOR_IA_TOKEN` (o MESMO
  valor de `APP_TOKEN`). A montagem do `.exe` os embute num
  `servidor_ia.json`, que nunca vai para o repositório.

## O que ainda recomendo

1. **Chave com faturamento ligado.** Numa chave gratuita a Google usa o
   conteúdo dos professores para melhorar os produtos dela e pessoas podem
   lê-lo (uma assinatura do Gemini não muda isso; só o faturamento ligado
   na chave). Trocar é só mudar o valor de `GEMINI_API_KEY` na Vercel e
   publicar de novo — o programa não muda.
2. No Google AI Studio / Cloud, um **orçamento com alerta e, se der, um
   teto de cota** no projeto da chave: é a defesa final contra abuso.
3. Girar o `APP_TOKEN` se houver suspeita de vazamento: novo valor na
   Vercel e no GitHub (`SERVIDOR_IA_TOKEN`), republicar o servidor e
   publicar uma versão nova do programa.

## Regras de defesa (ver `api/ia.py`)

- só POST com o `x-app-token` certo; a instrução é fixa e mora aqui;
- só os campos combinados da aula passam, com limite de tamanho; nunca
  nome de professor;
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

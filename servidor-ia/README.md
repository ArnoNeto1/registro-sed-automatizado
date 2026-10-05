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

## Publicar na Vercel (quando for a hora)

1. Crie um projeto na Vercel apontando para este repositório e escolha
   **Root Directory = `servidor-ia`** (assim só esta pasta é publicada).
2. Em *Settings → Environment Variables*, crie como **Sensitive**:
   - `GEMINI_API_KEY` — chave do Gemini **com faturamento ligado**. Numa
     chave gratuita a Google usa o conteúdo dos professores para melhorar
     os produtos dela; uma assinatura do Gemini não muda isso.
   - `APP_TOKEN` — um segredo longo e aleatório (ex.: 40+ caracteres).
   - `MODELO_IA` — opcional, para trocar o modelo.
3. Faça o deploy. O endereço fica `https://<projeto>.vercel.app/api/ia`.
4. No Google AI Studio / Cloud, ponha um **orçamento com alerta e, se der,
   um teto de cota** no projeto da chave: é a defesa final contra abuso.
5. Gire o `APP_TOKEN` se suspeitar de vazamento (e publique uma versão
   nova do programa com o segredo novo).

## Regras de defesa (ver `api/ia.py`)

- só POST com o `x-app-token` certo; a instrução é fixa e mora aqui;
- só os campos combinados da aula passam, com limite de tamanho; nunca
  nome de professor;
- erro cru da Google nunca volta; o conteúdo dos pedidos nunca é
  registrado.

## Atenção: `api/_ia_gemini.py` é cópia

É uma cópia **exata** de `ia_gemini.py` (raiz do repositório), porque esta
pasta é publicada sozinha. O teste `tests/test_servidor_ia.py` falha se
elas ficarem diferentes. Mexeu na raiz? Copie o arquivo por cima:

```bash
cp ia_gemini.py servidor-ia/api/_ia_gemini.py
```

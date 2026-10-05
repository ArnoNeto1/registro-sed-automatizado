# -*- coding: utf-8 -*-
"""
Roda o servidor da IA no SEU computador, só para testar — nada vai para a
internet além da chamada ao Gemini.

    python servidor-ia/rodar_local.py

Pede a chave do Gemini com a digitação escondida (ela fica só na memória
deste processo, não é gravada em arquivo nenhum) e atende em
http://127.0.0.1:8787/api/ia, só para este computador. Para o programa
falar com ele:

    SERVIDOR_IA_URL   = http://127.0.0.1:8787/api/ia
    SERVIDOR_IA_TOKEN = teste-local

Ctrl+C para parar.
"""

from __future__ import annotations

import getpass
import os
import pathlib
import sys
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "api"))
import ia  # noqa: E402

PORTA = 8787
TOKEN_LOCAL = "teste-local"  # só vale neste computador: o servidor escuta apenas 127.0.0.1


def main() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        chave = getpass.getpass("Cole a chave do Gemini (não aparece na tela) e tecle Enter: ").strip()
        if not chave:
            raise SystemExit("Sem chave, nada a fazer.")
        os.environ["GEMINI_API_KEY"] = chave
    os.environ.setdefault("APP_TOKEN", TOKEN_LOCAL)

    servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), ia.handler)
    print(f"\nServidor de teste no ar: http://127.0.0.1:{PORTA}/api/ia")
    print("Deixe esta janela aberta enquanto testa. Ctrl+C (ou fechar a janela) para parar.\n")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nParado.")


if __name__ == "__main__":
    main()

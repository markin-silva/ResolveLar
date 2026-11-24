#!/usr/bin/env python3
"""Gera JWTs (HS256) de teste para os perfis do Kong definidos em gateway/kong.tpl.yml.

O login normal é pelo ms-auth (POST /v1/auth/login). Este script serve para depurar sem a tela de entrada.

Só usa a biblioteca padrão. Exemplos:
    python3 scripts/generate_jwt.py                 # imprime os dois tokens
    python3 scripts/generate_jwt.py --hours 168     # validade de 7 dias
    TOKEN=$(python3 scripts/generate_jwt.py --only contratante)

O segredo vem de JWT_SECRET (padrão: o segredo de teste do .env.example). O Kong
casa o token com a credencial pela claim `iss` (= `key` da credencial).
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import time

DEFAULT_SECRET = "resolvelar-jwt-secret-2026"  # igual ao .env.example (somente teste local)

USERS = {
    "contratante": {"sub": "contratante_15", "iss": "contratante-key"},
    "prestador": {"sub": "prest_17", "iss": "prestador-key"},
}


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_token(secret: str, iss: str, sub: str, hours: float) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"iss": iss, "sub": sub, "iat": now, "exp": now + int(hours * 3600)}
    signing_input = ".".join(
        b64url(json.dumps(part, separators=(",", ":")).encode()) for part in (header, payload)
    )
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{b64url(signature)}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hours", type=float, default=24, help="validade em horas (padrão: 24)")
    parser.add_argument("--only", choices=USERS, help="imprime apenas o token deste perfil (sem rótulos)")
    args = parser.parse_args()

    secret = os.getenv("JWT_SECRET", DEFAULT_SECRET)
    if args.only:
        user = USERS[args.only]
        print(make_token(secret, user["iss"], user["sub"], args.hours))
        return

    for role, user in USERS.items():
        print(f"# {role} ({user['sub']}) — válido por {args.hours:g}h")
        print(f"export TOKEN_{role.upper()}={make_token(secret, user['iss'], user['sub'], args.hours)}\n")
    print('# Uso: curl -H "Authorization: Bearer $TOKEN_CONTRATANTE" http://localhost:8000/v1/contratante/me')


if __name__ == "__main__":
    main()

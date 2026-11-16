"""Gera configuração de operador. Senha lida interativamente, nunca em argv."""
import getpass
import hashlib
import json
import secrets

username = input("Nome do operador (ASCII, sem dois-pontos): ").strip()
if not username.isascii() or not username or ":" in username:
    raise SystemExit("Nome inválido.")
password = getpass.getpass("Senha ASCII (mínimo 16 caracteres): ")
if not password.isascii() or len(password) < 16 or password != getpass.getpass("Confirme a senha: "):
    raise SystemExit("Use senha ASCII de pelo menos 16 caracteres e confirmação igual.")
tenant_ids = [v.strip() for v in input("UUIDs de tenants autorizados, separados por vírgula: ").split(",") if v.strip()]
global_access = input("Permitir visão global de TODAS as empresas e filas? [sim/N]: ").strip().lower() == "sim"
if not global_access and not tenant_ids:
    raise SystemExit("Informe pelo menos um tenant para um operador restrito.")
salt = secrets.token_bytes(16)
digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000).hex()
print("\nArmazene o JSON abaixo em OPS_USERS_JSON, somente no servidor:")
print(json.dumps({username: {"password_hash": f"{salt.hex()}${digest}", "tenant_ids": tenant_ids, "global_access": global_access}}))

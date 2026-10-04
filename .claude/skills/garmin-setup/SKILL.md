---
name: garmin-setup
description: Configura o ambiente do garmin-trainer pela primeira vez (venv, dependencias, credenciais, login de teste).
---

# garmin-setup

Guia o usuario pela configuracao inicial do projeto garmin-trainer. Use quando o usuario pedir para
configurar, instalar ou preparar o projeto pela primeira vez, ou quando `login-test` falhar por falta
de credenciais.

## Passos

1. Verifique se existe `.venv/`. Se nao existir, crie com:
   `python -m venv .venv`
2. Instale as dependencias em modo editavel:
   `.venv/bin/python -m pip install -e .`
3. Verifique se `.env` existe. Se nao existir, copie `.env.example` para `.env` e peça ao usuario para
   preencher `GARMIN_EMAIL`, `GARMIN_PASSWORD` e `GEMINI_API_KEY`. Nunca leia ou exiba o conteudo de
   `.env` de volta para o usuario, e nunca commite esse arquivo.
4. Revise `config/athlete_profile.yaml` com o usuario: zonas de FC, objetivo de prova, dias disponiveis
   e preferencias. Ajuste os valores que o usuario informar.
5. Rode o teste de login:
   `.venv/bin/python -m garmin_trainer.cli login-test`
   Se pedir MFA, peça o codigo ao usuario e digite quando solicitado no terminal.
6. Confirme sucesso mostrando o nome retornado pelo Garmin Connect.

Se o login falhar, verifique a mensagem de erro (credenciais invalidas, MFA, ou bloqueio temporario da
Garmin por excesso de tentativas) antes de tentar novamente.

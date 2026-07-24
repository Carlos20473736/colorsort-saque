"""
ColorSort Saque - Backend
Replica a lógica do saque.py com interface web.
"""

import asyncio
import base64
import hashlib
import json
import math
import random
import time
import uuid
from typing import Any

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Constantes da API
BASE_URL = "https://api.colorsortgame.com"
APP_ID = "prod_v1_EJrxwTTmcwhF303T"
SECRET_KEY = "!OiMZyGo5hawC4mI@!"
AES_KEY = "$dWP2K8f=Kr0B4dU"
APP_VERSION = "1.0.8"
APP_VERSION_CODE = "108"
UNITY_VERSION = "2022.3.62f2c1"
NONCE_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789."


def generate_nonce(length: int = 16) -> str:
    return "".join(random.choice(NONCE_CHARSET) for _ in range(length))


def generate_api_sign(params: dict[str, str], country: str) -> str:
    params_to_sign = {
        key: str(value)
        for key, value in params.items()
        if key != "apiSign"
    }

    if params_to_sign.get("timeStamp"):
        params_to_sign["timeStamp"] = params_to_sign["timeStamp"][-6:]

    sorted_params = sorted(
        params_to_sign.items(),
        key=lambda item: item[0],
        reverse=True,
    )

    str_to_sign = country
    for key, value in sorted_params:
        str_to_sign += f"{key}={value}&"
    str_to_sign += f"key={SECRET_KEY}"

    return hashlib.md5(str_to_sign.encode("utf-8")).hexdigest().upper()


def aes_encrypt(data: str) -> str:
    cipher = AES.new(AES_KEY.encode("utf-8"), AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(data.encode("utf-8"), AES.block_size))
    return base64.b64encode(encrypted).decode("utf-8")


async def api_req(
    endpoint: str,
    data: dict[str, str] | None = None,
    token: str = "",
    device_id: str = "",
    proxy_url: str = "",
) -> dict[str, Any]:
    payload = {
        **(data or {}),
        "timeStamp": str(int(time.time())),
        "nonceStr": generate_nonce(),
        "appId": APP_ID,
    }
    payload["apiSign"] = generate_api_sign(payload, "BR")

    headers = {
        "User-Agent": (
            f"UnityPlayer/{UNITY_VERSION} "
            "(UnityWebRequest/1.0, libcurl/8.10.1-DEV)"
        ),
        "X-Unity-Version": UNITY_VERSION,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept-Encoding": "gzip, deflate",
        "qr-ver": APP_VERSION,
        "qr-ver-code": APP_VERSION_CODE,
        "qr-token": token,
        "qr-device": device_id,
        "qr-country": "BR",
        "qr-locale": "pt_BR",
        "qr-timezone": "Etc/GMT+4",
    }

    proxies = {}
    if proxy_url:
        proxies = {
            "http": proxy_url,
            "https": proxy_url,
        }

    response = await asyncio.to_thread(
        requests.post,
        BASE_URL + endpoint,
        data=payload,
        headers=headers,
        proxies=proxies if proxies else None,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


async def farm_cycle(level: int, token: str, device_id: str, proxy_url: str) -> dict[str, float | bool]:
    game_start = await api_req(
        "/v1/game/start",
        {"level": str(level), "version": "101"},
        token=token, device_id=device_id, proxy_url=proxy_url,
    )
    if game_start.get("code") != 1:
        return {"cash": 0.0, "ok": False}

    game_id = (game_start.get("data") or {}).get("game_id")

    gg_start = await api_req(
        "/v1/gg/start",
        {"gg_id": "18", "gg_code_id": "18", "ab_test": ""},
        token=token, device_id=device_id, proxy_url=proxy_url,
    )
    if gg_start.get("code") != 1:
        return {"cash": 0.0, "ok": False}

    gg_log_id = (gg_start.get("data") or {}).get("gg_log_id")
    gg_token = (gg_start.get("data") or {}).get("gg_token")

    await asyncio.sleep(18)
    await api_req(
        "/v1/gg/completed",
        {"gg_log_id": str(gg_log_id), "gg_token": str(gg_token)},
        token=token, device_id=device_id, proxy_url=proxy_url,
    )

    await asyncio.sleep(1.5)
    rev_data = aes_encrypt(
        json.dumps(
            {
                "gg_log_id": str(gg_log_id),
                "revenue": "0.35000000000000000",
                "piggy_cash": "0.00000000000000000",
                "piggy": "0",
                "piggy_rate": "0",
            },
            separators=(",", ":"),
        )
    )
    rev_response = await api_req(
        "/v1/gg/revenue", {"data": rev_data},
        token=token, device_id=device_id, proxy_url=proxy_url,
    )

    cash = 0.0
    if rev_response.get("code") == 1:
        cash = float((rev_response.get("data") or {}).get("revenue_cash") or 0)

    if game_id:
        win_data = aes_encrypt(
            json.dumps(
                {
                    "game_id": str(game_id),
                    "bottle": str(level),
                    "type": "Win",
                },
                separators=(",", ":"),
            )
        )
        await api_req(
            "/v1/game/end", {"data": win_data},
            token=token, device_id=device_id, proxy_url=proxy_url,
        )

    return {"cash": cash, "ok": True}


@app.get("/")
async def index():
    return FileResponse("templates/index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        # Receber configuração do cliente
        config = await websocket.receive_json()

        token = config.get("token", "").strip()
        device_id = config.get("device_id", "").strip()
        pix_key = config.get("pix_key", "").strip()
        proxy_url = config.get("proxy_url", "").strip()
        farm_target = int(config.get("farm_target", 160))
        num_saques = int(config.get("num_saques", 2))
        cpf = config.get("cpf", "46123509870").strip()

        if not token or not device_id or not pix_key:
            await websocket.send_json({"type": "error", "msg": "Token, Device ID e PIX são obrigatórios!"})
            return

        async def log(msg: str, type: str = "log"):
            await websocket.send_json({"type": type, "msg": msg})

        await log("═══════════════════════════════════════════════════════════")
        await log(f"   DeviceId: {device_id}")
        await log(f"   PIX: {pix_key}")
        await log(f"   Meta: Farm {farm_target} → {num_saques} saques de 25")
        await log("═══════════════════════════════════════════════════════════\n")

        # [1] Verificar saldo
        await log("💰 [1] Verificando saldo...", "step")
        balance = await api_req("/v1/withdraw/cash", {}, token=token, device_id=device_id, proxy_url=proxy_url)
        balance_data = balance.get("data") or {}
        current_cash = float((balance_data.get("balance") or {}).get("cash") or 0)
        await log(f"   Saldo: R$ {current_cash}")
        await log(f"   Níveis: {json.dumps(balance_data.get('levels'), ensure_ascii=False)}")

        # [2] Conta PIX
        await log("\n🔑 [2] Contas cadastradas...", "step")
        accounts = await api_req("/v1/withdraw/accounts", {}, token=token, device_id=device_id, proxy_url=proxy_url)
        accounts_data = accounts.get("data") or {}
        accs = accounts_data.get("accounts") or []

        account_id = ""
        pix_acc = next(
            (account for account in accs if account.get("account_no") == pix_key),
            None,
        )
        if pix_acc:
            account_id = str(pix_acc.get("account_id"))
            await log(f"   ✅ Conta PIX encontrada: {account_id}")
        elif accs:
            account_id = str(accs[0].get("account_id"))
            await log(f"   Usando primeira conta: {account_id}")
        else:
            await log("   Cadastrando PIX...")
            save = await api_req(
                "/v1/withdraw/save_account",
                {
                    "platform_id": "116",
                    "account_plat": "PIX",
                    "account_name": "Teste",
                    "account_no": pix_key,
                    "account_type": "B",
                    "document_id": cpf,
                    "account_phone": "",
                    "account_email": "",
                },
                token=token, device_id=device_id, proxy_url=proxy_url,
            )
            if save.get("code") == 1:
                account_id = str((save.get("data") or {}).get("account_id"))
                await log(f"   ✅ PIX cadastrado: {account_id}")
            else:
                await log(f"   ❌ Erro ao cadastrar PIX: {save.get('msg')}", "error")
                return

        if not account_id:
            await log("   ❌ Sem conta para sacar", "error")
            return

        await log(f"   Saldo atual: R$ {current_cash}")

        # [3] Farm
        if current_cash < farm_target:
            await log(f"\n🎮 [3] Farmando saldo (precisa R$ {farm_target})...", "step")
            cycles_needed = math.ceil((farm_target - current_cash) / 20) + 1
            level = 1

            for candidate_level in range(1, 101):
                game_start = await api_req(
                    "/v1/game/start",
                    {"level": str(candidate_level), "version": "101"},
                    token=token, device_id=device_id, proxy_url=proxy_url,
                )
                if game_start.get("code") == 1:
                    level = candidate_level
                    break

            await log(f"   Nível detectado: {level}")

            total_farmed = 0.0
            for index in range(cycles_needed):
                result = await farm_cycle(level, token, device_id, proxy_url)
                if result["ok"]:
                    total_farmed += result["cash"]
                    await log(f"   Ciclo {index + 1}: +R$ {float(result['cash']):.2f} (total: R$ {total_farmed:.2f})")
                else:
                    await log(f"   Ciclo {index + 1}: FALHOU")
                level += 1

                if (current_cash + total_farmed) >= farm_target:
                    await log(f"   ✅ Meta atingida!")
                    break

                await asyncio.sleep(2)

            new_balance = await api_req("/v1/withdraw/cash", {}, token=token, device_id=device_id, proxy_url=proxy_url)
            new_balance_data = new_balance.get("data") or {}
            new_cash = (new_balance_data.get("balance") or {}).get("cash")
            await log(f"   Novo saldo: R$ {new_cash}")

        # [4] Saques
        await log(f"\n💸 [4] Realizando {num_saques} saques de R$ 25...", "step")

        saques_ok = 0
        total_sacado = 0
        for i in range(num_saques):
            await log(f"\n   ── Saque {i+1}/{num_saques} (valor: 25, level_id: 1) ──")

            do_cash = await api_req(
                "/v1/withdraw/do_cash",
                {"account_id": account_id, "level_id": "1"},
                token=token, device_id=device_id, proxy_url=proxy_url,
            )

            if do_cash.get("code") == 1:
                do_cash_data = do_cash.get("data") or {}
                charge_id = str(do_cash_data.get("charge_id"))
                has_seq = bool(do_cash_data.get("$sequencesResult"))
                await log(f"   charge_id: {charge_id}")
                await log(f"   $sequencesResult: {has_seq}")

                if has_seq:
                    sequences = do_cash_data.get("$sequencesResult") or []
                    seq_data = sequences[1] if len(sequences) > 1 else {}
                    await log(f"   code: {seq_data.get('code')}")
                    await log(f"   currentRate: {seq_data.get('currentRate')}")

                await log("   do_charge...")
                do_charge = await api_req(
                    "/v1/withdraw/do_charge",
                    {"charge_id": charge_id, "ratio_level": "1"},
                    token=token, device_id=device_id, proxy_url=proxy_url,
                )

                if do_charge.get("code") == 1:
                    saques_ok += 1
                    total_sacado += 25
                    await log(f"\n   ✅✅✅ SAQUE {i+1} REALIZADO COM SUCESSO! ✅✅✅", "success")
                    await log(f"   Valor: R$ 25")
                    await log(f"   PIX: {pix_key}")
                else:
                    error_code = (do_charge.get("data") or {}).get("_errCode_")
                    await log(f"   ❌ do_charge falhou: {do_charge.get('msg')} (errCode: {error_code})", "error")
            else:
                await log(f"   ❌ do_cash falhou: {do_cash.get('msg')}", "error")

            # Pausa entre saques
            if i < num_saques - 1:
                await log("\n   Aguardando 3s antes do próximo saque...")
                await asyncio.sleep(3)

        await log("\n═══════════════════════════════════════════════════════════")
        await log(f"   FINALIZADO", "done")
        await log(f"   Saques OK: {saques_ok}/{num_saques}")
        await log(f"   Total sacado: R$ {total_sacado}")
        await log("═══════════════════════════════════════════════════════════")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "msg": f"❌ ERRO: {str(e)}"})
        except:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(__import__("os").environ.get("PORT", 8000)))

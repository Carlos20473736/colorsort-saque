# ColorSort Saque Automático

Interface web para farm + saque automático do ColorSort.

## Deploy no Railway

1. Faça fork ou conecte este repositório ao Railway
2. O Railway vai detectar automaticamente o `Dockerfile` ou `nixpacks.toml`
3. Deploy automático

## Funcionalidades

- Farm automático de saldo
- Saque via PIX (1 ou 2 saques de R$ 25)
- Suporte a proxy SOCKS5
- Log em tempo real via WebSocket
- Interface responsiva

## Execução Local

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Acesse: http://localhost:8000

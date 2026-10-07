bot-social/
├── .env
├── config.py              # paleta, fontes, tamanhos, limites
├── core/
│   ├── pipeline.py        # criar_post(tema) -> orquestra tudo
│   ├── texto.py           # LLMs com fallback (JSON validado)
│   ├── imagem/            # adaptadores por provedor + fallback
│   ├── render.py          # HTML -> PNG (Playwright)
│   └── instagram.py       # publicação (etapa final)
├── templates/             # dica.html, citacao.html, capa.html
├── entradas/
│   ├── telegram_bot.py    # aprovação com botões (polling)
│   └── agendado.py        # roda por cron / GitHub Actions
└── saida/                 # PNGs gerados
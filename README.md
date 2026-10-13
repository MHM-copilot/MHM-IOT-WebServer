# MHM-IOT-WebServer

Aplicação web para catalogar binários de firmware para dispositivos IoT e disponibilizar as versões `.bin` e `.elf` em um fluxo protegido por senha.

## Visão geral

O projeto usa FastAPI + Uvicorn + Jinja2 e foi pensado como um template de referência para:

- listar firmwares por dispositivo e versão;
- manter configuracao em JSONL + variaveis de ambiente;
- servir os artefatos de firmware de forma segura;
- rodar em container Docker com poucas dependencias.

## Arquitetura

- `app/main.py`: ponto de entrada da API e rotas HTTP;
- `app/config.py`: leitura da configuracao, resolucao de caminhos e carregamento do JSONL;
- `app/templates/`: templates HTML renderizados por Jinja2;
- `config/firmware.jsonl`: catalogo de firmwares em formato JSONL;
- `firmware/`: diretorio que guarda os binarios e ELF locais;
- `Dockerfile` e `docker-compose.yml`: execucao em container;
- `.env` / `.env.example`: configuracao de runtime.

## Configuracao

A aplicacao aceita configuracao por variaveis de ambiente ou por arquivo JSONL.

### Variaveis de ambiente

Crie um `.env` a partir do `.env.example`:

```bash
cp .env.example .env
```

Variaveis principais:

- `APP_TITLE`: titulo exibido na UI
- `APP_HOST`: host do uvicorn
- `APP_PORT`: porta HTTP
- `APP_SECRET_KEY`: chave interna da aplicacao
- `APP_PROTECTED_USERNAME`: usuario para acessos protegidos
- `APP_PROTECTED_PASSWORD`: senha para acessar `.bin` e `.elf`
- `APP_CONFIG_PATH`: caminho do arquivo JSONL de firmware
- `APP_FIRMWARE_ROOT`: raiz dos arquivos binarios e ELF

### JSONL de catalogo

Arquivo de exemplo:

```json
{"id":"esp32-sensor-v1","name":"ESP32 Sensor v1","version":"1.0.0","device_family":"esp32","description":"Main sensor firmware","binary_path":"esp32-sensor-v1.bin","elf_path":"esp32-sensor-v1.elf","enabled":true}
```

Cada linha representa uma entrada de firmware. A aplicacao le cada registro e monta uma pagina de detalhe para cada ID.

## Execucao local

Instale as dependencias:

```bash
python -m pip install -r requirements.txt
```

Inicie a aplicacao:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Acesse:

- http://localhost:8000/ para ver o catalogo publico
- http://localhost:8000/firmware/esp32-sensor-v1 para ver o detalhe
- rotas protegidas sob `/protected/download/{firmware_id}/{artifact}` exigem Basic Auth

## Acesso protegido

As rotas de download protegidas exigem autenticacao HTTP Basic.

Exemplo:

- Usuario: `admin`
- Senha: `change-me`

A configuracao deve ser alterada em `.env` para ambientes reais.

## Docker

### Build

```bash
docker build -t mhm-iot-webserver .
```

### Execucao

```bash
docker run --rm -p 8000:8000 --env-file .env mhm-iot-webserver
```

Ou usando Docker Compose:

```bash
docker compose up --build
```

## Estrutura de arquivos de firmware

Coloque o arquivo binario e o ELF correspondente no diretorio `firmware/` e referencie os nomes em `config/firmware.jsonl`.

Exemplo:

```text
firmware/
  esp32-sensor-v1.bin
  esp32-sensor-v1.elf
  esp32-gateway-v2.bin
  esp32-gateway-v2.elf
```

## Observacoes

- O projeto foi desenhado para ser extensivel e parametrizavel.
- A parte publica mostra o catalogo e os metadados.
- Apenas a entrega dos artefatos em `/protected/download` exige autenticao.
- A estrutura foi organizada para facilitar uso em ambientes de CI/CD e deploy containerizado.

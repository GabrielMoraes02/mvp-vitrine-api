# Vitrine API

API REST do MVP Vitrine. O serviço gerencia produtos em SQLite, fornece indicadores para o painel administrativo e integra o catálogo público da Fake Store API.

## Tecnologias

- Python 3.12
- FastAPI
- SQLite
- HTTPX
- Pytest
- Docker

## Rotas

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Verificar a disponibilidade do serviço |
| GET | `/api/products` | Listar, pesquisar, filtrar e ordenar produtos |
| GET | `/api/products/{id}` | Consultar um produto |
| POST | `/api/products` | Cadastrar um produto local |
| PATCH | `/api/products/{id}` | Atualizar parcialmente um produto |
| DELETE | `/api/products/{id}` | Excluir um produto |
| POST | `/api/products/sync` | Sincronizar produtos da Fake Store |
| GET | `/api/dashboard` | Obter métricas administrativas |
| GET/POST | `/api/categories` | Listar e cadastrar categorias |
| PATCH/DELETE | `/api/categories/{id}` | Editar e excluir categorias |
| GET/POST | `/api/subcategories` | Listar e cadastrar subcategorias |
| PATCH/DELETE | `/api/subcategories/{id}` | Editar e excluir subcategorias |

Todas as rotas, parâmetros e modelos podem ser testados no Swagger em `/docs`.

## Execução com Docker

```bash
docker build -t vitrine-api .
docker run --rm -p 8000:8000 -v vitrine-data:/app/data vitrine-api
```

Acesse:

- Swagger: `http://localhost:8000/docs`
- Saúde da API: `http://localhost:8000/health`

## Execução local

Crie um ambiente virtual e instale as dependências:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

## Testes

```bash
pytest -q
```

Os testes validam o CRUD completo, persistência, métricas e sincronização externa simulada.

## Configuração

| Variável | Padrão | Finalidade |
|---|---|---|
| `DATABASE_PATH` | `data/vitrine.db` | Caminho do banco SQLite |
| `FAKE_STORE_URL` | `https://fakestoreapi.com` | URL base da API externa |
| `FRONTEND_ORIGINS` | Portas locais 3000 e 4173 | Origens permitidas pelo CORS |

## Integração externa

`POST /api/products/sync` consulta `GET https://fakestoreapi.com/products`, normaliza os campos e faz uma atualização idempotente pelo identificador externo. Produtos criados localmente continuam separados dos produtos importados.

## Estrutura

```text
.
├── app/
│   ├── services/fake_store.py
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   └── models.py
├── tests/test_products.py
├── Dockerfile
├── requirements.txt
└── requirements-dev.txt
```

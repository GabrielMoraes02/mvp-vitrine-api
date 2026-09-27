# Vitrine API

API REST da plataforma Vitrine. O serviço gerencia produtos, pedidos e despesas em SQLite, fornece relatórios financeiros para o painel administrativo e integra um catálogo público externo.

Interface web: [github.com/GabrielMoraes02/vitrine-frontend](https://github.com/GabrielMoraes02/vitrine-frontend)

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
| POST | `/api/orders` | Registrar pedido, calcular total e baixar estoque |
| GET | `/api/orders` | Listar pedidos recentes |
| GET | `/api/reports/sales` | Consolidar vendas, despesas, saldo e indicadores |
| POST | `/api/expenses` | Registrar uma despesa |
| DELETE | `/api/expenses/{id}` | Excluir uma despesa |

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

Os testes validam o CRUD completo, persistência, métricas, sincronização externa, pedidos, baixa de estoque e relatório financeiro.

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

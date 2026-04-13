# Controle de Mochila — TI Armazém Paraíba

Sistema interno para controle de saída e retorno de mochilas de equipamentos de TI.

## Stack
- **Backend:** Django 5.x
- **Frontend:** HTML + CSS (design system próprio, dark theme)
- **Banco de dados:** SQLite (pronto para PostgreSQL)
- **Estáticos em produção:** WhiteNoise

---

## Instalação rápida

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar ambiente
cp .env.example .env
# Editar .env com suas configurações

# 3. Migrations
python manage.py migrate

# 4. Criar superusuário
python manage.py createsuperuser

# 5. Coletar estáticos (produção)
python manage.py collectstatic --noinput

# 6. Rodar
DJANGO_DEBUG=True python manage.py runserver
```

Acesse em: http://localhost:8000

---

## Níveis de acesso

| Nível       | Criar/Editar/Excluir | Gerenciar Usuários | Painel Admin |
|-------------|---------------------|--------------------|--------------|
| Usuário     | ❌                  | ❌                | ❌           |
| Supervisor  | ✅                  | ❌                | ❌           |
| Admin       | ✅                  | ✅                | ✅           |

---

## Variáveis de ambiente (`.env`)

| Variável                 | Descrição                          | Padrão                        |
|--------------------------|------------------------------------|-------------------------------|
| `DJANGO_SECRET_KEY`      | Chave secreta da aplicação         |  Falta Gerar uma nova!        |
| `DJANGO_DEBUG`           | Modo debug (`True`/`False`)        | `False`                       |
| `DJANGO_ALLOWED_HOSTS`   | Hosts permitidos (espaço separado) | `localhost 127.0.0.1`         |

---
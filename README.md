# Controle de Mochila — TI Armazém Paraíba

Sistema interno de gestão de saída e retorno de mochilas de equipamentos de TI, desenvolvido para a equipe de tecnologia do Armazém Paraíba.

---

## Visão Geral

O sistema permite registrar e acompanhar viagens de técnicos de TI às lojas, controlando quais equipamentos saíram, com quem, para onde, e se retornaram corretamente. Cada saída gera um **checklist automático** baseado nos itens da mochila utilizada, permitindo rastrear o status de cada equipamento na saída e no retorno.

---

## Funcionalidades

- **Dashboard** com visão em tempo real das viagens em andamento, estatísticas do mês e acesso rápido a mochilas
- **Gestão de Viagens** — registro de saídas, acompanhamento de status e finalização com checklist
- **Checklist de Equipamentos** — conferência item a item na saída e no retorno, com campo de observações
- **Gestão de Mochilas** — kits de equipamentos pré-configurados com quantidades
- **Gestão de Itens** — cadastro de equipamentos com soft delete (itens em uso não são deletados)
- **Gestão de Lojas** — unidades atendidas com histórico de viagens
- **Controle de Acesso** — três níveis de permissão (Admin, Supervisor, Usuário)
- **Política de Senha** — troca obrigatória no primeiro acesso, reset por administrador
- **Auditoria** — todas as ações críticas são registradas no Django AdminLog
- **Proteção contra concorrência** — mochila em uso não pode ser reservada por duas viagens simultâneas

---

## Arquitetura

O projeto segue uma arquitetura em camadas com separação clara de responsabilidades:

```
HTTP Request
     │
     ▼
  views.py          → Orquestração HTTP apenas (sem lógica de negócio)
     │
     ▼
  services/         → Toda a lógica de negócio
  ├── viagem_service.py
  ├── mochila_service.py
  └── usuario_service.py
     │
     ▼
  permissions.py    → Todas as regras de acesso centralizadas
     │
     ▼
  models.py         → Apenas dados, relações e validações simples
```

**Princípios aplicados:**
- Views apenas orquestram — nunca decidem regras de negócio
- Services são a única fonte de verdade para operações críticas
- Permissions são sempre verificadas em `permissions.py`, nunca inline nas views
- Soft delete em vez de deleção física para registros referenciados

---

## Regras de Negócio

### Viagens
- Uma mochila não pode estar em duas viagens simultâneas (`select_for_update` previne race conditions)
- O checklist é gerado automaticamente com os itens e quantidades exatos da mochila no momento da saída
- Viagens finalizadas têm checklist bloqueado para edição
- Usuários comuns só visualizam suas próprias viagens

### Mochilas
- Mochilas em viagem ativa não podem ser desativadas
- Ao editar uma mochila, as quantidades existentes dos itens são preservadas
- Deleção é sempre soft delete (`ativo=False`)

### Usuários e Senhas
- Novos usuários sempre recebem a senha padrão `Dti@paraiba` automaticamente
- Todo novo usuário é obrigado a trocar a senha no primeiro login (middleware garante isso)
- Supervisores **nunca** têm acesso a operações de senha
- Reset de senha é exclusivo do Administrador
- A nova senha não pode ser igual à senha padrão do sistema

### Exclusões (Soft Delete)
- Itens, Mochilas e Lojas nunca são deletados fisicamente se houver referências
- A flag `ativo=False` os oculta das listagens e seletores sem quebrar o histórico

---

## Níveis de Acesso

| Operação                        | Usuário | Supervisor | Admin |
|---------------------------------|---------|------------|-------|
| Visualizar viagens próprias     | ✅      | ✅         | ✅    |
| Visualizar todas as viagens     | ❌      | ✅         | ✅    |
| Criar/finalizar viagens         | ❌      | ✅         | ✅    |
| Editar checklist                | ❌      | ✅         | ✅    |
| Gerenciar mochilas/lojas/itens  | ❌      | ✅         | ✅    |
| Criar/editar usuários           | ❌      | ❌         | ✅    |
| Resetar senha de usuário        | ❌      | ❌         | ✅    |
| Painel administrativo Django    | ❌      | ❌         | ✅    |

---

## Stack Tecnológica

| Camada         | Tecnologia                            |
|----------------|---------------------------------------|
| Backend        | Django 5.x (Python)                   |
| Banco de dados | SQLite (dev) / PostgreSQL (produção)  |
| Autenticação   | Django Auth + Groups + Permissions    |
| Frontend       | HTML5 + CSS3 (design system próprio)  |
| Tipografia     | DM Sans + DM Mono (Google Fonts)      |
| Ícones         | Font Awesome 6                        |
| Estáticos      | WhiteNoise (produção)                 |
| Sessões        | Django Sessions (8h de expiração)     |

---

## Estrutura do Projeto

```
controle-mochila/
├── controle_mochila/         # Configurações do projeto Django
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
│
├── core/                     # App principal
│   ├── models.py             # Modelos de dados
│   ├── views.py              # Views (apenas HTTP)
│   ├── forms.py              # Validação de inputs
│   ├── urls.py               # Roteamento
│   ├── permissions.py        # Regras de acesso centralizadas
│   ├── mixins.py             # Mixins de autenticação/contexto
│   ├── middleware.py         # ForcePasswordChangeMiddleware
│   ├── admin.py              # Painel administrativo
│   ├── tests.py              # Testes unitários
│   │
│   ├── services/             # Camada de negócio
│   │   ├── viagem_service.py
│   │   ├── mochila_service.py
│   │   └── usuario_service.py
│   │
│   └── management/
│       └── commands/
│           └── setup_groups.py   # Configura grupos e permissões
│
├── templates/                # Templates HTML
│   ├── base.html
│   └── core/
│       ├── dashboard.html
│       ├── viagem_list.html
│       ├── viagem_detail.html
│       ├── viagem_form.html
│       ├── mochila_list.html
│       ├── mochila_detail.html
│       ├── mochila_form.html
│       ├── item_list.html
│       ├── loja_list.html
│       ├── usuario_list.html
│       ├── login.html
│       ├── trocar_senha.html
│       └── confirm_delete.html
│
├── static/
│   ├── css/
│   │   ├── tokens.css        # Design tokens e variáveis CSS
│   │   ├── sidebar.css
│   │   ├── layout.css
│   │   ├── buttons.css
│   │   ├── cards.css
│   │   ├── tables.css
│   │   ├── forms.css
│   │   ├── components.css
│   │   └── responsive.css
│   └── js/
│       └── base.js
│
├── requirements.txt
├── manage.py
└── .env.example
```

---

## Instalação e Execução

### Pré-requisitos
- Python 3.11+
- pip

### Passos

```bash
# 1. Clone o repositório
git clone 'https://github.com/devthayron/controle_mochila_ti.git'
cd controle-mochila

# 2. Crie e ative o ambiente virtual
python -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure o ambiente
cp .env.example .env
# Edite .env e defina DJANGO_SECRET_KEY com uma chave segura

# 5. Execute as migrations
python manage.py migrate

# 6. Configure os grupos e permissões
python manage.py setup_groups

# 7. Crie o superusuário (administrador)
python manage.py createsuperuser

# 8. Execute o servidor
DJANGO_DEBUG=True python manage.py runserver
```

Acesse em: **http://localhost:8000**

O superusuário criado terá acesso total. Para criar outros usuários, acesse o painel de **Usuários** na sidebar.

### Produção

```bash
# Coletar arquivos estáticos
python manage.py collectstatic --noinput

# Variáveis de ambiente obrigatórias em produção:
# DJANGO_SECRET_KEY=<chave-segura-gerada>
# DJANGO_DEBUG=False
# DJANGO_ALLOWED_HOSTS=seudominio.com

# Servidor WSGI recomendado
gunicorn controle_mochila.wsgi:application --bind 0.0.0.0:8000
```

---

## Variáveis de Ambiente

| Variável               | Descrição                          | Padrão                    |
|------------------------|------------------------------------|---------------------------|
| `DJANGO_SECRET_KEY`    | Chave secreta da aplicação         | `dev-key` ⚠️ trocar!     |
| `DJANGO_DEBUG`         | Modo debug (`True`/`False`)        | `True`                    |
| `DJANGO_ALLOWED_HOSTS` | Hosts permitidos (separados por espaço) | `127.0.0.1 localhost` |

> **⚠️ Atenção:** Nunca use `dev-key` em produção. Gere uma chave segura com:
> ```bash
> python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
> ```

---

## Executar Testes

```bash
python manage.py test core
```

Os testes cobrem:
- Camada de permissões (admin, supervisor, usuário)
- Services de viagem (criar, finalizar, checklist)
- Atribuição e leitura de grupos de acesso

---

## Fluxo Principal do Sistema

```
Admin cria usuário
       │
       ▼
Usuário faz login → middleware verifica must_change_password
       │
       ▼ (primeiro acesso)
Troca de senha obrigatória
       │
       ▼
Dashboard — visão geral
       │
Supervisor registra Nova Viagem
       │  (seleciona responsável, loja, mochila)
       ▼
Checklist gerado automaticamente
       │
       ▼
Técnico vai à loja
       │
       ▼
Retorno: checklist atualizado (saída OK / retorno OK / observações)
       │
       ▼
Supervisor finaliza viagem → status = finalizada → checklist bloqueado
```

---

## Melhorias Futuras

- **Quantidades editáveis no formulário de mochila** — permitir definir quantidade de cada item diretamente na tela de criação/edição
- **Exportação de relatórios** — PDF/Excel de histórico de viagens por período ou loja
- **PostgreSQL** — migração do SQLite para banco mais robusto em produção
- **Dashboard avançado** — gráficos de uso de mochilas por período

---

## Licença

Sistema interno — uso exclusivo da equipe de TI do Armazém Paraíba.

# Testes Não Funcionais de Desempenho (Load Testing com Locust)

Este diretório contém a suíte de testes de carga desenvolvida para a avaliação da característica de qualidade **Eficiência de Desempenho (*Performance Efficiency*)** do `django-helpdesk` (FGA0314 - Testes de Software - 2026.2).

## Estrutura do Diretório
- `locustfile.py`: Script de automação em Python contendo os 3 cenários de carga (`PublicTicketReaderUser`, `PublicTicketSubmitterUser` e `StaffTicketListUser`).
- `resultados/`: Arquivos CSV brutos com séries temporais, métricas de percentis ($p50$, $p95$, $p99$), vazão (RPS) e relatórios de falhas coletados durante a execução dos testes.

## Como Executar

### 1. Iniciar o servidor do django-helpdesk:
```bash
python manage.py runserver 127.0.0.1:8080
```

### 2. Executar o Locust com Interface Web:
```bash
locust -f testes_nao_funcionais/locustfile.py --host=http://127.0.0.1:8080
```
Acesse a interface no navegador em `http://localhost:8089`, configure 30 usuários com taxa de subida de 5 usuários/s e clique em **Start swarming**.

### 3. Executar em modo Headless (por cenário):
```bash
# Cenário 1: Leitura Pública
locust -f testes_nao_funcionais/locustfile.py PublicTicketReaderUser --headless -u 30 -r 5 -t 20s --host=http://127.0.0.1:8080 --csv=testes_nao_funcionais/resultados/cenario1_leitura

# Cenário 2: Escrita Concorrente
locust -f testes_nao_funcionais/locustfile.py PublicTicketSubmitterUser --headless -u 30 -r 5 -t 20s --host=http://127.0.0.1:8080 --csv=testes_nao_funcionais/resultados/cenario2_escrita

# Cenário 3: Listagem e Filtragem Staff
locust -f testes_nao_funcionais/locustfile.py StaffTicketListUser --headless -u 30 -r 5 -t 20s --host=http://127.0.0.1:8080 --csv=testes_nao_funcionais/resultados/cenario3_listagem
```

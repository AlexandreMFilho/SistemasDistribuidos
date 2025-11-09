# 💬 Trabalho Final – Sistemas Distribuídos  

## Tema: Sistema de Chat Distribuído com Tolerância a Falhas  

---

### 🧭 Enunciado  

Desenvolver um **sistema de mensagens instantâneas distribuído e descentralizado (sem servidor central)**, onde os nós da rede possam **enviar e receber mensagens em tempo real**, mantendo **resiliência a falhas** e **reorganização automática** em caso de desconexões.

---


## 🧩 Arquitetura Peer-to-Peer  

✔️ Cada instância do programa é simultaneamente **cliente e servidor**.  

- Cada nó abre um socket TCP (`servidor()`) e aceita conexões de outros nós.  
- As mensagens são repassadas em anel (Ring Topology).  
- O líder é apenas um nó eleito dinamicamente, **não um servidor central fixo**.  

✔️ Comunicação é descentralizada:  

- Mensagens são encaminhadas de nó a nó via `enviar_para_proximo()`.  
- Cada mensagem tem um UUID único para evitar duplicações (armazenadas em `cache`).  
- O chat é broadcast em anel — todos os nós recebem.  

🔹 **Vantagem:** A rede continua funcional mesmo se o líder cair — o sistema se reorganiza.  

---

## 📡 Entrada Multicast na Rede  

✔️ O **multicast** permite que novos nós descubram a rede sem saber o IP do líder.  

- O primeiro nó executa `multicast_listener()` e se torna líder.  
- Novos nós enviam `DISCOVER:<ip>:<porta>` via `multicast_discovery()`.  
- Apenas o líder responde com `JOIN|<vizinho_anterior>|<líder>`.

✔️ O nó recém-chegado conecta-se ao anel via o vizinho informado e anuncia:

```python
cliente_envio(username, f"Olá, entrei na rede! Meu ID é {meu_ip}:{minha_porta}")
```

✔️ O líder adiciona o novo nó à lista global e redistribui automaticamente a lista:

```python
NETWORK_MEMBERS.append(novo_no)
distribuir_lista_membros()
```

🟢 **Resultado:** a rede cresce dinamicamente e mantém consistência entre todos os nós.

---

## 👑 Papel do Coordenador (Líder)

### Funções principais:

1. **Gerenciar entrada de novos nós** via `multicast_listener()`.
2. **Distribuir lista de membros** da rede (`@LIST_BUILD` e `@LIST_UPDATE`).
3. **Enviar heartbeat periódico** para indicar que está ativo.
4. **Gerenciar saída e reconexão** de nós (`@EXIT`, `@RECONNECT`).
5. **Iniciar nova eleição** em caso de falhas.

---

## ❤️ Integração do Heartbeat  

✔️ O líder envia `@HEARTBEAT` a cada 5 segundos:  

```python
if LIDER == MEU_ID:
    cliente_envio(username, "@HEARTBEAT")
```

✔️ Os demais nós atualizam `ultimo_heartbeat` ao receber:  

```python
ultimo_heartbeat = time.time()
```

✔️ O monitor (`monitorar_heartbeat`) verifica continuamente:  

- Se passar **>10 segundos** sem heartbeat → inicia eleição.  

✔️ Threads daemon:  

- `enviar_heartbeat()` e `monitorar_heartbeat()` são threads independentes (`daemon=True`).  

🔹 **Fluxo automático:**  
- O líder envia batimentos somente após ser eleito.  
- Quando o líder cai, os outros detectam ausência e iniciam eleição.  
- O novo líder automaticamente passa a enviar batimentos.

🟢 **Vantagem:** Nenhum batimento é enviado prematuramente, evitando ruído na rede.

---

## ⚙️ Eleição de Novo Coordenador  

✔️ O sistema implementa um **algoritmo de eleição em anel**.  

- Cada nó envia `@LIDER>><meu_id>` quando detecta ausência de líder.  
- A mensagem circula até retornar ao iniciador.  
- O nó iniciador reconhece-se como novo líder:  

```python
if ip_iniciador == MEU_ID and STATUSLIDER == "waiting":
    LIDER = MEU_ID
    STATUSLIDER = "elected"
```

✔️ Após ser eleito:
- O novo líder anuncia: `@LIDER>>{LIDER}>>ELECTED`.
- Reconstrói e distribui a lista de membros.
- Inicia automaticamente o envio de heartbeats e multicast listener.

🟢 **Comportamento:** a eleição é totalmente descentralizada, sem intervenção manual.

---

## 🧠 Tolerância a Falhas  

✔️ **Falha do líder:**  
- Detectada por ausência de heartbeat.  
- Dispara nova eleição automaticamente.  
- Novo líder assume e restabelece multicast + batimentos.

✔️ **Saída de nó:**  
- O líder recebe `@EXIT>><id>` e calcula novo anel:  

```python
cliente_envio(username, f"@RECONNECT>>{predecessor}>>{sucessor}")
```
- Redistribui lista com `@LIST_UPDATE`.

✔️ **Falha de nó intermediário:**  
- O anel é reconstituído, e os vizinhos são reconectados automaticamente.

🟢 **Resiliência garantida:** a rede continua operando mesmo com quedas parciais.

---

## 🧾 Histórico Consistente  

✔️ Toda mensagem contém um **UUID único** (`msg_id`):  

```python
msg_id = str(uuid.uuid4())
```

✔️ As mensagens são armazenadas no `cache` (estrutura `deque`):  
- Garante que cada mensagem circule apenas uma vez.  
- Evita duplicação e inconsistência no chat.  

✔️ As mensagens são repassadas até completar o ciclo (`Ring Broadcast`).  
Assim, todos os nós veem o mesmo histórico.  

---

## 🧪 Demonstração Prática  

- Testado em rede real (várias máquinas) e local (127.0.0.1).  
- Primeira instância assume papel de líder automaticamente.  
- Novos nós se conectam via multicast (`DISCOVER`) e são integrados ao anel.  
- Mensagens trocadas são exibidas em todos os terminais.  
- Eleição ocorre automaticamente quando o líder é encerrado (`Ctrl+C` ou `FIM`).  

---

## 🧰 Comandos Disponíveis

| Comando | Função |
|----------|--------|
| **@LIDER** | Inicia manualmente uma eleição |
| **@LIST** | Solicita atualização da lista de membros |
| **@MEMBERS** | Mostra os nós conhecidos |
| **FIM** | Sai da rede de forma organizada |
| **@HELP** | Mostra a lista de comandos |

---

## ⚙️ Modos de Execução  

Use argumentos opcionais para habilitar logs:  

```bash
python3 trabalhoFinal.py debug
python3 trabalhoFinal.py heartbeat
python3 trabalhoFinal.py
```

- `debug` → Mostra logs detalhados da rede, multicast e eleição.  
- `heartbeat` → Mostra apenas batimentos e falhas de líder.  
- padrão → Apenas chat e comandos.  

---

## 📚 Tecnologias Utilizadas  

- **Python 3.10+**  
- **Sockets TCP/UDP**  
- **Multicast IP (UDP)**  
- **Threads (threading)**  
- **Estruturas de dados deque e UUID**  

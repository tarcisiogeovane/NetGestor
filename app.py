from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
from datetime import datetime, timedelta
from librouteros import connect
from librouteros.exceptions import LibRouterosError

app = Flask(__name__)

# Configuração inicial da conexão com a RouterBoard (pode ser sobrescrita depois)
RB_HOST = "177.37.161.1"
RB_USER = "tarciso"
RB_PASSWORD = "tarciso"

# Função para conectar à RouterBoard
def connect_to_routerboard(host=RB_HOST, user=RB_USER, password=RB_PASSWORD):
    try:
        api = connect(username=user, password=password, host=host, port=8728)
        print(f"Conexão com a RouterBoard ({host}) bem-sucedida!")
        return api
    except LibRouterosError as e:
        print(f"Erro ao conectar à RouterBoard ({host}): {e}")
        return None

# Função para conectar ao banco de dados
def get_db_connection():
    conn = sqlite3.connect('netgestor.db')
    conn.row_factory = sqlite3.Row
    return conn

# Função para contar clientes por status
def count_clients():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM clients")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM clients WHERE status = 'active'")
    active = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM clients WHERE status = 'inactive'")
    inactive = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM clients WHERE msg_pendencia = 1")
    pending = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM clients WHERE msg_bloqueio = 1")
    blocked = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM clients WHERE isento_mensalidade = 1")
    exempt = cursor.fetchone()[0] or 0
    
    conn.close()
    return {"total": total, "active": active, "inactive": inactive, "pending": pending, "blocked": blocked, "exempt": exempt}

# Função para sincronizar clientes da RouterBoard com o banco de dados local
def sync_routerboard_clients(host=RB_HOST, user=RB_USER, password=RB_PASSWORD):
    api = connect_to_routerboard(host, user, password)
    if not api:
        return False, "Falha na conexão com a RouterBoard."

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Buscar clientes ativos da RouterBoard (via DHCP Leases)
        api_clients = api.path("/ip/dhcp-server/lease")
        clientes_rb = [dict(client) for client in api_clients]
        print(f"Clientes retornados pela RouterBoard: {clientes_rb}")

        # Verificar se há clientes antes de prosseguir
        if not clientes_rb:
            print("Nenhum cliente encontrado na RouterBoard.")
            return False, "Nenhum cliente encontrado na RouterBoard."

        # Sincronizar com o banco de dados local
        for client in clientes_rb:
            client_id = client.get('mac-address', '').replace(':', '')[:12]  # Usar MAC como ID único
            nome = client.get('host-name', f"Cliente-{client_id[:6]}")
            login = client.get('host-name', f"cliente-{client_id[:6]}").lower() if client.get('host-name') else f"cliente-{client_id[:6]}"
            ip = client.get('address', '').split('/')[0] if client.get('address') else ''
            status = 'active' if client.get('status') == 'bound' else 'inactive'
            data_cadastro = datetime.now().strftime('%Y-%m-%d')

            # Verificar se o cliente já existe no banco
            cursor.execute("SELECT id FROM clients WHERE id = ?", (client_id,))
            existing_client = cursor.fetchone()

            if not existing_client:
                # Inserir novo cliente
                cursor.execute('''
                    INSERT INTO clients (id, nome, login, dia_venc, ip, servidor, plano, status, msg_pendencia, msg_bloqueio, data_cadastro, isento_mensalidade)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (client_id, nome, login, "10", ip, "RouterBoard", "Desconhecido", status, 0, 0, data_cadastro, 0))
                print(f"Cliente {client_id} inserido no banco de dados.")
            else:
                # Atualizar cliente existente
                cursor.execute('''
                    UPDATE clients 
                    SET nome = ?, login = ?, ip = ?, status = ?
                    WHERE id = ?
                ''', (nome, login, ip, status, client_id))
                print(f"Cliente {client_id} atualizado no banco de dados.")

        conn.commit()
        return True, f"{len(clientes_rb)} clientes sincronizados com sucesso."
    except Exception as e:
        print(f"Erro ao sincronizar clientes da RouterBoard: {e}")
        return False, f"Erro ao sincronizar: {str(e)}"
    finally:
        conn.close()
        if api:
            api.close()

# Rota para a página inicial (Dashboard)
@app.route('/')
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Pagamentos por Dia (últimos 6 dias)
    pagamentos = []
    for i in range(6):
        dia = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        cursor.execute("SELECT SUM(valor) FROM pagamentos WHERE DATE(data) = ?", (dia,))
        valor = cursor.fetchone()[0] or 0.0
        pagamentos.append({"dia": dia, "valor": valor})
    pagamentos.reverse()

    # Novos Clientes e Desativados (últimos 6 dias)
    novos_clientes = []
    desativados = []
    for i in range(6):
        dia = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        cursor.execute("SELECT COUNT(*) FROM clients WHERE DATE(data_cadastro) = ? AND status = 'active'", (dia,))
        novos = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM clients WHERE DATE(data_cadastro) = ? AND status = 'inactive'", (dia,))
        desativ = cursor.fetchone()[0]
        novos_clientes.append({"dia": dia, "quantidade": novos})
        desativados.append({"dia": dia, "quantidade": desativ})
    novos_clientes.reverse()
    desativados.reverse()

    # Despesas (Mensal - apenas do mês atual)
    current_month = datetime.now().strftime('%Y-%m')
    cursor.execute("SELECT COUNT(*), SUM(valor) FROM despesas WHERE strftime('%Y-%m', data) = ?", (current_month,))
    todas = cursor.fetchone()
    cursor.execute("SELECT COUNT(*), SUM(valor) FROM despesas WHERE status = 'paga' AND strftime('%Y-%m', data) = ?", (current_month,))
    pagas = cursor.fetchone()
    cursor.execute("SELECT COUNT(*), SUM(valor) FROM despesas WHERE status = 'em_aberto' AND strftime('%Y-%m', data) = ?", (current_month,))
    em_aberto = cursor.fetchone()
    cursor.execute("SELECT COUNT(*), SUM(valor) FROM despesas WHERE status = 'em_atraso' AND strftime('%Y-%m', data) = ?", (current_month,))
    em_atraso = cursor.fetchone()

    # Chamados (Mensal - apenas do mês atual)
    cursor.execute("SELECT COUNT(*) FROM chamados WHERE strftime('%Y-%m', data) = ?", (current_month,))
    todos_chamados = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chamados WHERE status = 'novo' AND strftime('%Y-%m', data) = ?", (current_month,))
    novos_chamados = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chamados WHERE status = 'em_aberto' AND strftime('%Y-%m', data) = ?", (current_month,))
    em_aberto_chamados = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chamados WHERE status = 'aguard_cliente' AND strftime('%Y-%m', data) = ?", (current_month,))
    aguard_cliente = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chamados WHERE status = 'aguard_resposta' AND strftime('%Y-%m', data) = ?", (current_month,))
    aguard_resposta = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chamados WHERE status = 'finalizado' AND strftime('%Y-%m', data) = ?", (current_month,))
    finalizados = cursor.fetchone()[0]

    conn.close()

    dashboard_data = {
        "pagamentos_por_dia": pagamentos,
        "novos_clientes": novos_clientes,
        "desativados": desativados,
        "despesas": {
            "todas": {"quantidade": todas[0], "valor": todas[1] or 0.0},
            "pagas": {"quantidade": pagas[0], "valor": pagas[1] or 0.0},
            "em_aberto": {"quantidade": em_aberto[0], "valor": em_aberto[1] or 0.0},
            "em_atraso": {"quantidade": em_atraso[0], "valor": em_atraso[1] or 0.0},
        },
        "chamados": {
            "todos": todos_chamados,
            "novos": novos_chamados,
            "em_aberto": em_aberto_chamados,
            "aguard_cliente": aguard_cliente,
            "aguard_resposta": aguard_resposta,
            "finalizados": finalizados,
        }
    }

    return render_template('dashboard.html', page_title="Dashboard", dashboard_data=dashboard_data)

# Rota para Clientes
@app.route('/clientes')
def clientes():
    # Sincronizar clientes da RouterBoard com o banco de dados
    sync_success, sync_message = sync_routerboard_clients()

    # Conectar ao banco de dados local
    conn = get_db_connection()
    cursor = conn.cursor()

    # Buscar clientes do banco de dados local
    cursor.execute("SELECT * FROM clients")
    clientes_local = cursor.fetchall()

    # Buscar clientes diretamente da RouterBoard
    api = connect_to_routerboard()
    clientes_rb = []
    if api:
        try:
            api_clients = api.path("/ip/dhcp-server/lease")
            clientes_rb = [dict(client) for client in api_clients]
            print(f"Clientes exibidos na rota /clientes: {clientes_rb}")
        except Exception as e:
            print(f"Erro ao buscar clientes da RouterBoard: {e}")
        finally:
            api.close()

    conn.close()
    return render_template('clientes/clientes.html', 
                          page_title="Clientes", 
                          clientes_local=clientes_local, 
                          clientes_rb=clientes_rb, 
                          sync_success=sync_success,
                          sync_message=sync_message)

# Rota para configurar as credenciais da RouterBoard
@app.route('/configurar_routerboard', methods=['GET', 'POST'])
def configurar_routerboard():
    if request.method == 'POST':
        global RB_HOST, RB_USER, RB_PASSWORD
        RB_HOST = request.form.get('rb_host')
        RB_USER = request.form.get('rb_user')
        RB_PASSWORD = request.form.get('rb_password')

        # Testar a conexão com as novas credenciais
        sync_success, sync_message = sync_routerboard_clients(RB_HOST, RB_USER, RB_PASSWORD)
        return render_template('configurar_routerboard.html', 
                              page_title="Configurar RouterBoard", 
                              sync_success=sync_success, 
                              sync_message=sync_message)

    return render_template('configurar_routerboard.html', page_title="Configurar RouterBoard")

# Rota para Clientes > Todos
@app.route('/clientes/todos', methods=['GET', 'POST'])
def clientes_todos():
    # Sincronizar clientes da RouterBoard antes de listar
    sync_success, sync_message = sync_routerboard_clients()

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        selected_clients = request.form.getlist('selected_clients')

        for client_id in selected_clients:
            if action == "activate_pending":
                cursor.execute("UPDATE clients SET msg_pendencia = 1 WHERE id = ?", (client_id,))
            elif action == "activate_blocked":
                cursor.execute("UPDATE clients SET msg_bloqueio = 1 WHERE id = ?", (client_id,))
            elif action == "deactivate_msg":
                cursor.execute("UPDATE clients SET msg_pendencia = 0, msg_bloqueio = 0 WHERE id = ?", (client_id,))
            elif action == "activate":
                cursor.execute("UPDATE clients SET status = 'active' WHERE id = ?", (client_id,))
            elif action == "deactivate":
                cursor.execute("UPDATE clients SET status = 'inactive' WHERE id = ?", (client_id,))
            elif action == "delete":
                cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))

        conn.commit()

        # Salvar novo cliente (do popup)
        if action == "save_new_client":
            cursor.execute("SELECT MAX(id) FROM clients")
            max_id = cursor.fetchone()[0]
            new_id = str(int(max_id) + 1).zfill(3) if max_id else "001"
            new_client = {
                "id": new_id,
                "nome": request.form.get('nome_completo'),
                "login": request.form.get('login'),
                "dia_venc": request.form.get('dia_vencimento'),
                "ip": request.form.get('ip_hotspot') or request.form.get('ip_pppoe'),
                "servidor": request.form.get('servidor'),
                "plano": request.form.get('plano'),
                "status": 'active' if request.form.get('status') == 'ativo' else 'inactive',
                "msg_pendencia": 1 if request.form.get('msg_pendencia_automatica') == 'sim' else 0,
                "msg_bloqueio": 1 if request.form.get('msg_bloqueio_automatica') == 'sim' else 0,
                "data_cadastro": datetime.now().strftime('%Y-%m-%d'),
                "isento_mensalidade": 1 if request.form.get('isento_mensalidade') == 'sim' else 0
            }
            cursor.execute('''
                INSERT INTO clients (id, nome, login, dia_venc, ip, servidor, plano, status, msg_pendencia, msg_bloqueio, data_cadastro, isento_mensalidade)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (new_client["id"], new_client["nome"], new_client["login"], new_client["dia_venc"],
                  new_client["ip"], new_client["servidor"], new_client["plano"], new_client["status"],
                  new_client["msg_pendencia"], new_client["msg_bloqueio"], new_client["data_cadastro"],
                  new_client["isento_mensalidade"]))
            conn.commit()

        conn.close()
        return redirect(url_for('clientes_todos'))

    # Buscar clientes do banco de dados local
    cursor.execute("SELECT * FROM clients")
    clients = cursor.fetchall()
    counts = count_clients()

    # Buscar clientes diretamente da RouterBoard para exibição
    api = connect_to_routerboard()
    clientes_rb = []
    if api:
        try:
            api_clients = api.path("/ip/dhcp-server/lease")
            clientes_rb = [dict(client) for client in api_clients if 'address' in client]
            print(f"Clientes exibidos na rota /clientes/todos: {clientes_rb}")
        except Exception as e:
            print(f"Erro ao buscar clientes da RouterBoard: {e}")
        finally:
            api.close()

    conn.close()
    return render_template('clientes/todos.html', page_title="Todos os Clientes", clients=clients, counts=counts, clientes_rb=clientes_rb, sync_message=sync_message)

# Rota para Clientes > Contratos
@app.route('/clientes/contratos')
def clientes_contratos():
    return render_template('clientes/contratos.html', page_title="Contratos")

# Rota para Clientes > Mapa de Clientes
@app.route('/clientes/mapa')
def clientes_mapa():
    return render_template('clientes/mapa.html', page_title="Mapa de Clientes")

# Rota para Clientes > Clientes Online
@app.route('/clientes/online')
def clientes_online():
    return render_template('clientes/online.html', page_title="Clientes Online")

# Rotas para outras abas
@app.route('/atendimento')
def atendimento():
    return render_template('atendimento.html', page_title="Atendimento")

@app.route('/chamados')
def chamados():
    return render_template('chamados.html', page_title="Chamados")

@app.route('/financeiro')
def financeiro():
    return render_template('financeiro.html', page_title="Financeiro")

@app.route('/rede')
def rede():
    return render_template('rede.html', page_title="Rede")

@app.route('/ferramentas')
def ferramentas():
    return render_template('ferramentas.html', page_title="Ferramentas")

@app.route('/cadastros')
def cadastros():
    return render_template('cadastros.html', page_title="Cadastros")

@app.route('/sistema')
def sistema():
    return render_template('sistema.html', page_title="Sistema")

if __name__ == '__main__':
    app.run(debug=True)
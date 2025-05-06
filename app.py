from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
from datetime import datetime, timedelta
from librouteros import connect
from librouteros.exceptions import LibRouterosError
from dotenv import load_dotenv
import os

load_dotenv()  # Carrega variáveis do arquivo .env

app = Flask(__name__)

# Configuração inicial da conexão com a RouterBoard a partir de variáveis de ambiente
RB_HOST = os.getenv("RB_HOST", "177.37.161.1")
RB_USER = os.getenv("RB_USER", "tarciso")
RB_PASSWORD = os.getenv("RB_PASSWORD", "tarciso")

# Função para conectar ao banco de dados
def get_db_connection():
    conn = sqlite3.connect('netgestor.db')
    conn.row_factory = sqlite3.Row
    return conn

# Função para inicializar o banco de dados
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Criar tabela servidores se não existir
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS servidores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            porta INTEGER NOT NULL,
            usar_vpn BOOLEAN NOT NULL,
            ip TEXT,
            usuario TEXT,
            senha TEXT
        )
    ''')
    
    # Criar outras tabelas necessárias (caso não existam)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            login TEXT NOT NULL,
            dia_venc TEXT,
            ip TEXT,
            servidor TEXT,
            plano TEXT,
            status TEXT,
            msg_pendencia INTEGER,
            msg_bloqueio INTEGER,
            data_cadastro TEXT,
            isento_mensalidade INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT,
            valor REAL,
            data TEXT,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            valor REAL,
            data TEXT,
            status TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chamados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT,
            data TEXT,
            status TEXT,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Função para se conectar à RouterBoard
def connect_to_routerboard(host, user, password, port):
    try:
        api = connect(username=user, password=password, host=host, port=port)
        print(f"Conexão com a RouterBoard ({host}:{port}) bem-sucedida!")
        return api
    except LibRouterosError as e:
        print(f"Erro ao conectar à RouterBoard ({host}:{port}): {e}")
        return None

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
def sync_routerboard_clients():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM servidores")
    servidores = cursor.fetchall()
    conn.close()

    total_clients_synced = 0
    sync_messages = []

    for servidor in servidores:
        host = servidor['ip']
        user = servidor['usuario']
        password = servidor['senha']
        port = servidor['porta']

        api = connect_to_routerboard(host, user, password, port)
        if not api:
            sync_messages.append(f"Falha na conexão com {servidor['nome']} ({host}). Verifique as credenciais ou a conexão.")
            continue

        try:
            # Tentar buscar clientes via DHCP Leases
            api_clients_dhcp = api.path("/ip/dhcp-server/lease")
            clientes_dhcp = [dict(client) for client in api_clients_dhcp if 'address' in client]
            print(f"Clientes DHCP retornados de {host}: {clientes_dhcp}")

            # Tentar buscar clientes via PPP Active (fallback)
            api_clients_ppp = api.path("/ppp/active")
            clientes_ppp = [dict(client) for client in api_clients_ppp if 'address' in client]
            print(f"Clientes PPP retornados de {host}: {clientes_ppp}")

            clientes_rb = clientes_dhcp + clientes_ppp
            if not clientes_rb:
                sync_messages.append(f"Nenhum cliente encontrado em {servidor['nome']} ({host}).")
                continue

            # Sincronizar com o banco de dados local, associando ao servidor
            for client in clientes_rb:
                client_id = client.get('mac-address', client.get('caller-id', '')).replace(':', '')[:12]
                nome = client.get('host-name', f"Cliente-{client_id[:6]}")
                login = client.get('host-name', f"cliente-{client_id[:6]}").lower() if client.get('host-name') else f"cliente-{client_id[:6]}"
                ip = client.get('address', '').split('/')[0] if client.get('address') else ''
                status = 'active' if client.get('status') == 'bound' or client.get('uptime') else 'inactive'
                data_cadastro = datetime.now().strftime('%Y-%m-%d')

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM clients WHERE id = ?", (client_id,))
                existing_client = cursor.fetchone()

                if not existing_client:
                    cursor.execute('''
                        INSERT INTO clients (id, nome, login, dia_venc, ip, servidor, plano, status, msg_pendencia, msg_bloqueio, data_cadastro, isento_mensalidade)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (client_id, nome, login, "10", ip, servidor['nome'], "Desconhecido", status, 0, 0, data_cadastro, 0))
                    print(f"Cliente {client_id} inserido do servidor {servidor['nome']}.")
                else:
                    cursor.execute('''
                        UPDATE clients 
                        SET nome = ?, login = ?, ip = ?, status = ?, servidor = ?
                        WHERE id = ?
                    ''', (nome, login, ip, status, servidor['nome'], client_id))
                    print(f"Cliente {client_id} atualizado do servidor {servidor['nome']}.")
                conn.commit()
                conn.close()

            total_clients_synced += len(clientes_rb)
            sync_messages.append(f"{len(clientes_rb)} clientes sincronizados de {servidor['nome']} ({host}).")

        except Exception as e:
            sync_messages.append(f"Erro ao sincronizar {servidor['nome']} ({host}): {str(e)}")
        finally:
            if api:
                api.close()

    if total_clients_synced > 0:
        return True, "\n".join(sync_messages)
    return False, "\n".join(sync_messages) if sync_messages else "Nenhum servidor configurado ou sincronizado."

# Rota para a página inicial (Dashboard)
@app.route('/')
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    pagamentos = []
    for i in range(6):
        dia = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        cursor.execute("SELECT SUM(valor) FROM pagamentos WHERE DATE(data) = ?", (dia,))
        valor = cursor.fetchone()[0] or 0.0
        pagamentos.append({"dia": dia, "valor": valor})
    pagamentos.reverse()

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

    current_month = datetime.now().strftime('%Y-%m')
    cursor.execute("SELECT COUNT(*), SUM(valor) FROM despesas WHERE strftime('%Y-%m', data) = ?", (current_month,))
    todas = cursor.fetchone()
    cursor.execute("SELECT COUNT(*), SUM(valor) FROM despesas WHERE status = 'paga' AND strftime('%Y-%m', data) = ?", (current_month,))
    pagas = cursor.fetchone()
    cursor.execute("SELECT COUNT(*), SUM(valor) FROM despesas WHERE status = 'em_aberto' AND strftime('%Y-%m', data) = ?", (current_month,))
    em_aberto = cursor.fetchone()
    cursor.execute("SELECT COUNT(*), SUM(valor) FROM despesas WHERE status = 'em_atraso' AND strftime('%Y-%m', data) = ?", (current_month,))
    em_atraso = cursor.fetchone()

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
    sync_success, sync_message = sync_routerboard_clients()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients")
    clientes_local = cursor.fetchall()
    api = connect_to_routerboard(RB_HOST, RB_USER, RB_PASSWORD, 8728)
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
    return render_template('clientes/clientes.html', page_title="Clientes", clientes_local=clientes_local, clientes_rb=clientes_rb, sync_success=sync_success, sync_message=sync_message)

# Rota para configurar os servidores (incluindo RouterBoard)
@app.route('/rede/servidores', methods=['GET', 'POST'])
def configurar_servidores():
    if request.method == 'POST':
        if 'action' in request.form and request.form['action'] == 'save_server':
            nome = request.form.get('nome')
            porta = request.form.get('porta')
            usar_vpn = request.form.get('usar_vpn') == 'sim'
            ip = request.form.get('ip') if not usar_vpn else None
            usuario = request.form.get('usuario') if not usar_vpn else None
            senha = request.form.get('senha') if not usar_vpn else None

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO servidores (nome, porta, usar_vpn, ip, usuario, senha)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (nome, porta, usar_vpn, ip, usuario, senha))
            conn.commit()
            conn.close()
            return redirect(url_for('configurar_servidores'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM servidores")
    servidores = cursor.fetchall()
    conn.close()
    return render_template('rede/servidores.html', page_title="Servidores", servidores=servidores)

# Rota para Clientes > Todos
@app.route('/clientes/todos', methods=['GET', 'POST'])
def clientes_todos():
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
    cursor.execute("SELECT * FROM clients")
    clients = cursor.fetchall()
    counts = count_clients()
    api = connect_to_routerboard(RB_HOST, RB_USER, RB_PASSWORD, 8728)
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients")
    clients = cursor.fetchall()
    conn.close()
    return render_template('clientes/contratos.html', page_title="Contratos", clients=clients)

# Rota para Clientes > Mapa de Clientes
@app.route('/clientes/mapa')
def clientes_mapa():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients")
    clients = cursor.fetchall()
    conn.close()
    return render_template('clientes/mapa.html', page_title="Mapa de Clientes", clients=clients)

# Rota para Clientes > Clientes Online
@app.route('/clientes/online')
def clientes_online():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients WHERE status = 'active'")
    clients = cursor.fetchall()
    conn.close()
    return render_template('clientes/online.html', page_title="Clientes Online", clients=clients)

# Rotas para outras abas
@app.route('/atendimento')
def atendimento():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients")
    clients = cursor.fetchall()
    conn.close()
    return render_template('atendimento.html', page_title="Atendimento", clients=clients)

@app.route('/chamados')
def chamados():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients")
    clients = cursor.fetchall()
    conn.close()
    return render_template('chamados.html', page_title="Chamados", clients=clients)

@app.route('/financeiro')
def financeiro():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients")
    clients = cursor.fetchall()
    conn.close()
    return render_template('financeiro.html', page_title="Financeiro", clients=clients)

@app.route('/rede')
def rede():
    return render_template('rede.html', page_title="Rede")

@app.route('/ferramentas')
def ferramentas():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients")
    clients = cursor.fetchall()
    conn.close()
    return render_template('ferramentas.html', page_title="Ferramentas", clients=clients)

@app.route('/cadastros')
def cadastros():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients")
    clients = cursor.fetchall()
    conn.close()
    return render_template('cadastros.html', page_title="Cadastros", clients=clients)

@app.route('/sistema')
def sistema():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients")
    clients = cursor.fetchall()
    conn.close()
    return render_template('sistema.html', page_title="Sistema", clients=clients)

# Inicializar o banco de dados na inicialização do aplicativo
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True)
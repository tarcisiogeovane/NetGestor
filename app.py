from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)

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
    return render_template('clientes/clientes.html', page_title="Clientes")

# Rota para Clientes > Todos
@app.route('/clientes/todos', methods=['GET', 'POST'])
def clientes_todos():
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
            new_client = {
                "id": str(len(clients) + 1).zfill(3),
                "nome": request.form.get('nome_completo'),
                "login": request.form.get('login'),
                "dia_venc": request.form.get('dia_vencimento'),
                "ip": request.form.get('ip_hotspot') or request.form.get('ip_pppoe'),
                "servidor": request.form.get('servidor'),
                "plano": request.form.get('plano'),
                "status": request.form.get('status'),
                "msg_pendencia": request.form.get('msg_pendencia_automatica') == 'sim',
                "msg_bloqueio": request.form.get('msg_bloqueio_automatica') == 'sim',
                "data_cadastro": datetime.now().strftime('%Y-%m-%d')
            }
            cursor.execute('''
                INSERT INTO clients (id, nome, login, dia_venc, ip, servidor, plano, status, msg_pendencia, msg_bloqueio, data_cadastro)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (new_client["id"], new_client["nome"], new_client["login"], new_client["dia_venc"],
                  new_client["ip"], new_client["servidor"], new_client["plano"], new_client["status"],
                  new_client["msg_pendencia"], new_client["msg_bloqueio"], new_client["data_cadastro"]))
            conn.commit()

        conn.close()
        return redirect(url_for('clientes_todos'))

    cursor.execute("SELECT * FROM clients")
    clients = cursor.fetchall()
    counts = count_clients()
    conn.close()
    return render_template('clientes/todos.html', page_title="Todos os Clientes", clients=clients, counts=counts)

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
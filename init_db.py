import sqlite3

# Conectar ao banco de dados (será criado se não existir)
conn = sqlite3.connect('netgestor.db')
cursor = conn.cursor()

# Tabela de Clientes
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
        msg_pendencia BOOLEAN,
        msg_bloqueio BOOLEAN,
        data_cadastro TEXT
    )
''')

# Tabela de Pagamentos
cursor.execute('''
    CREATE TABLE IF NOT EXISTS pagamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id TEXT,
        data TEXT,
        valor REAL,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )
''')

# Tabela de Despesas
cursor.execute('''
    CREATE TABLE IF NOT EXISTS despesas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        valor REAL,
        status TEXT,
        data TEXT
    )
''')

# Tabela de Chamados
cursor.execute('''
    CREATE TABLE IF NOT EXISTS chamados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id TEXT,
        status TEXT,
        data TEXT,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )
''')

# Inserir dados iniciais para teste
# Clientes
cursor.executemany('''
    INSERT OR IGNORE INTO clients (id, nome, login, dia_venc, ip, servidor, plano, status, msg_pendencia, msg_bloqueio, data_cadastro)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', [
    ("001", "João Silva", "joao.silva", "10", "192.168.1.101", "Servidor A", "100 Mbps", "active", False, False, "2025-04-25"),
    ("002", "Maria Oliveira", "maria.oliveira", "15", "192.168.1.102", "Servidor B", "50 Mbps", "inactive", False, False, "2025-04-26")
])

# Pagamentos
cursor.executemany('''
    INSERT INTO pagamentos (client_id, data, valor) VALUES (?, ?, ?)
''', [
    ("001", "2025-04-25", 300.00),
    ("001", "2025-04-26", 450.00),
    ("002", "2025-04-27", 200.00),
    ("002", "2025-04-28", 600.00),
    ("001", "2025-04-29", 350.00),
    ("002", "2025-04-30", 500.00)
])

# Despesas
cursor.executemany('''
    INSERT INTO despesas (valor, status, data) VALUES (?, ?, ?)
''', [
    (100.00, "paga", "2025-04-01"),
    (150.00, "paga", "2025-04-02"),
    (200.00, "em_aberto", "2025-04-03"),
    (250.00, "em_aberto", "2025-04-04"),
    (300.00, "em_atraso", "2025-04-05")
])

# Chamados
cursor.executemany('''
    INSERT INTO chamados (client_id, status, data) VALUES (?, ?, ?)
''', [
    ("001", "novo", "2025-04-01"),
    ("001", "em_aberto", "2025-04-02"),
    ("002", "aguard_cliente", "2025-04-03"),
    ("002", "aguard_resposta", "2025-04-04"),
    ("001", "finalizado", "2025-04-05")
])

# Salvar e fechar
conn.commit()
conn.close()

print("Banco de dados inicializado com sucesso!")
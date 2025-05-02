import sqlite3

# Conectar ao banco de dados
conn = sqlite3.connect('netgestor.db')
cursor = conn.cursor()

# Criar uma nova tabela com a coluna isento_mensalidade
cursor.execute('''
    CREATE TABLE clients_new (
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
        data_cadastro TEXT,
        isento_mensalidade BOOLEAN DEFAULT 0
    )
''')

# Copiar os dados da tabela antiga para a nova
cursor.execute('''
    INSERT INTO clients_new (id, nome, login, dia_venc, ip, servidor, plano, status, msg_pendencia, msg_bloqueio, data_cadastro)
    SELECT id, nome, login, dia_venc, ip, servidor, plano, status, msg_pendencia, msg_bloqueio, data_cadastro
    FROM clients
''')

# Excluir a tabela antiga
cursor.execute('DROP TABLE clients')

# Renomear a nova tabela
cursor.execute('ALTER TABLE clients_new RENAME TO clients')

# Salvar e fechar
conn.commit()
conn.close()

print("Migração concluída com sucesso!")
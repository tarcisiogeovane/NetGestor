from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def dashboard():
    return render_template('dashboard.html', page_title='Dashboard')

@app.route('/clientes')
@app.route('/clientes/todos')
def clientes_todos():
    return render_template('clientes/todos.html', page_title='Todos os Clientes')

@app.route('/clientes/contratos')
def clientes_contratos():
    return render_template('clientes/contratos.html', page_title='Contratos')

@app.route('/clientes/mapa')
def clientes_mapa():
    return render_template('clientes/mapa.html', page_title='Mapa de Clientes')

@app.route('/clientes/online')
def clientes_online():
    return render_template('clientes/online.html', page_title='Clientes Online')

@app.route('/atendimento')
def atendimento():
    return render_template('atendimento.html', page_title='Atendimento')

@app.route('/chamados')
def chamados():
    return render_template('chamados.html', page_title='Chamados')

@app.route('/financeiro')
def financeiro():
    return render_template('financeiro.html', page_title='Financeiro')

@app.route('/rede')
def rede():
    return render_template('rede.html', page_title='Rede')

@app.route('/ferramentas')
def ferramentas():
    return render_template('ferramentas.html', page_title='Ferramentas')

@app.route('/cadastros')
def cadastros():
    return render_template('cadastros.html', page_title='Cadastros')

@app.route('/sistema')
def sistema():
    return render_template('sistema.html', page_title='Sistema')

if __name__ == '__main__':
    app.run(debug=True)
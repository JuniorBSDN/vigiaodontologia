from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin import auth as firebase_auth
import os
import json
import bcrypt
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Firebase via variável de ambiente
firebase_credentials_json = os.getenv("FIREBASE_CREDENTIALS")
if firebase_credentials_json:
    try:
        cred_dict = json.loads(firebase_credentials_json)
    except json.JSONDecodeError as e:
        print(f"Erro ao decodificar JSON da variável FIREBASE_CREDENTIALS: {e}")
        exit(1)
else:
    try:
        with open('path/to/your/serviceAccountKey.json', 'r') as f:
            cred_dict = json.load(f)
    except FileNotFoundError:
        print("Erro: FIREBASE_CREDENTIALS não definida e serviceAccountKey.json não encontrado.")
        print("Por favor, defina a variável de ambiente FIREBASE_CREDENTIALS no Vercel ou forneça o arquivo de credenciais localmente.")
        exit(1)

cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)

db = firestore.client()
usuarios_ref = db.collection('USUARIO')
agendamentos_ref = db.collection('AGENDAMENTOS')

# ---
## Endpoints
# ---

@app.route("/cadastrar_usuario", methods=["POST"])
def cadastrar_usuario():
    dados = request.get_json()
    nome = dados.get("nome")
    email = dados.get("email")
    senha = dados.get("senha")

    if not nome or not email or not senha:
        return jsonify({"erro": "Campos obrigatórios faltando."}), 400

    ja_existe = usuarios_ref.where("email", "==", email).get()
    if ja_existe:
        return jsonify({"erro": "E-mail já cadastrado."}), 409

    try:
        hashed_password = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt())

        usuarios_ref.add({
            "nome": nome,
            "email": email,
            "senha": hashed_password.decode('utf-8')
        })
        return jsonify({"mensagem": "Usuário cadastrado com sucesso."}), 201
    except Exception as e:
        print(f"Erro ao cadastrar usuário: {e}")
        return jsonify({"erro": "Erro interno ao cadastrar usuário."}), 500


@app.route("/completar_perfil", methods=["POST"])
def completar_perfil():
    dados = request.get_json()
    email = dados.get("email")

    if not email:
        return jsonify({"erro": "E-mail é obrigatório."}), 400

    consulta = usuarios_ref.where("email", "==", email).get()
    if not consulta:
        return jsonify({"erro": "Usuário não encontrado."}), 404

    usuario_doc_ref = consulta[0].reference

    campos = {
        "cpf": dados.get("cpf"),
        "telefone": dados.get("telefone"),
        "data_nascimento": dados.get("data_nascimento"),
        "sexo": dados.get("sexo"),
        "endereco": dados.get("endereco"),
        "plano": dados.get("plano"),
        "quick_notes": dados.get("quick_notes")
    }

    campos_para_atualizar = {k: v for k, v in campos.items() if v is not None}

    try:
        usuario_doc_ref.update(campos_para_atualizar)
        return jsonify({"mensagem": "Perfil atualizado com sucesso."}), 200
    except Exception as e:
        print(f"Erro ao atualizar perfil: {e}")
        return jsonify({"erro": "Erro interno ao atualizar perfil."}), 500


@app.route("/login_usuario", methods=["POST"])
def login_usuario():
    dados = request.get_json()
    email = dados.get("email")
    senha = dados.get("senha")

    if not email or not senha:
        return jsonify({"erro": "Email e senha obrigatórios."}), 400

    consulta = usuarios_ref.where("email", "==", email).get()
    if not consulta:
        return jsonify({"erro": "Usuário ou senha incorretos."}), 401

    usuario_doc = consulta[0]
    usuario_data = usuario_doc.to_dict()
    senha_hash_salva = usuario_data.get("senha")

    if senha_hash_salva and bcrypt.checkpw(senha.encode('utf-8'), senha_hash_salva.encode('utf-8')):
        usuario_data.pop("senha", None)
        return jsonify({
            "mensagem": "Login válido",
            "usuario": usuario_data
        }), 200
    else:
        return jsonify({"erro": "Usuário ou senha incorretos."}), 401


@app.route("/recuperar-senha", methods=["POST"])
def recuperar_senha():
    dados = request.get_json()
    email = dados.get("email")

    if not email:
        return jsonify({"erro": "O e-mail é obrigatório."}), 400

    try:
        # Envia o e-mail de redefinição de senha usando o Firebase Admin SDK
        firebase_auth.generate_password_reset_link(email)
        return jsonify({"mensagem": "Link de redefinição de senha enviado para o seu e-mail."}), 200
    except Exception as e:
        print(f"Erro ao enviar e-mail de redefinição de senha: {e}")
        return jsonify({"erro": "Não foi possível enviar o e-mail. Por favor, verifique se o endereço está correto e tente novamente."}), 400


@app.route("/agendar_consulta", methods=["POST"])
def agendar_consulta():
    dados = request.get_json()
    required_fields = ["email", "data_consulta", "hora_consulta", "dentista", "procedimento"]
    for field in required_fields:
        if field not in dados or not dados[field]:
            return jsonify({"erro": f"Campo '{field}' é obrigatório."}), 400

    email_paciente = dados.get("email")
    agendamento_data = {
        "email_paciente": email_paciente,
        "data_consulta": dados.get("data_consulta"),
        "hora_consulta": dados.get("hora_consulta"),
        "dentista": dados.get("dentista"),
        "procedimento": dados.get("procedimento"),
        "status": "Pendente",
        "valor": dados.get("valor", "R$ 0,00"),
        "forma": dados.get("forma", "A Definir"),
        "paciente": dados.get("paciente", "N/A"),
        "timestamp": firestore.SERVER_TIMESTAMP
    }

    if "relato_cliente" in dados: agendamento_data["relato_cliente"] = dados.get("relato_cliente")
    if "diabetes" in dados: agendamento_data["diabetes"] = dados.get("diabetes")
    if "hipertensao" in dados: agendamento_data["hipertensao"] = dados.get("hipertensao")
    if "cardio" in dados: agendamento_data["cardio"] = dados.get("cardio")
    if "alergias" in dados: agendamento_data["alergias"] = dados.get("alergias")
    if "coagulacao" in dados: agendamento_data["coagulacao"] = dados.get("coagulacao")
    if "none" in dados: agendamento_data["none"] = dados.get("none")
    if "medication" in dados: agendamento_data["medication"] = dados.get("medication")
    if "dentes_afetados" in dados: agendamento_data["dentes_afetados"] = dados.get("dentes_afetados")

    try:
        agendamentos_ref.add(agendamento_data)
        return jsonify({"mensagem": "Agendamento realizado com sucesso."}), 201
    except Exception as e:
        print(f"Erro ao agendar consulta: {e}")
        return jsonify({"erro": "Erro interno ao agendar consulta."}), 500


@app.route("/financeiro/dados", methods=["GET"])
def get_dados_financeiros():
    ano = request.args.get("ano", type=int)
    mes = request.args.get("mes", type=int)

    if not ano or not mes:
        return jsonify({"erro": "Ano e mês são obrigatórios."}), 400

    try:
        data_inicio = datetime(ano, mes, 1)
        if mes == 12:
            data_fim = datetime(ano + 1, 1, 1)
        else:
            data_fim = datetime(ano, mes + 1, 1)

        query_ref = agendamentos_ref.where('data_consulta', '>=', data_inicio.strftime('%Y-%m-%d')).where('data_consulta', '<', data_fim.strftime('%Y-%m-%d'))
        docs = query_ref.stream()

        pagamentos = []
        recebido = 0.0
        pendente = 0.0

        for doc in docs:
            doc_data = doc.to_dict()
            valor_str = doc_data.get("valor", "R$ 0,00").replace("R$", "").replace(".", "").replace(",", ".").strip()
            valor = float(valor_str)
            status = doc_data.get("status", "Pendente")

            if status == "Pago":
                recebido += valor
            elif status == "Pendente":
                pendente += valor

            pagamentos.append({
                "paciente": doc_data.get("paciente", "N/A"),
                "servico": doc_data.get("procedimento", "N/A"),
                "data": doc_data.get("data_consulta", "N/A"),
                "valor": f"R$ {valor:.2f}".replace('.', ','),
                "status": status,
                "forma": doc_data.get("forma", "N/A")
            })

        total_faturado = recebido + pendente

        return jsonify({
            "resumo": {
                "recebido": f"R$ {recebido:.2f}".replace('.', ','),
                "pendente": f"R$ {pendente:.2f}".replace('.', ','),
                "total_faturado": f"R$ {total_faturado:.2f}".replace('.', ',')
            },
            "pagamentos": pagamentos
        }), 200

    except Exception as e:
        print(f"Erro ao obter dados financeiros: {e}")
        return jsonify({"erro": "Erro interno ao obter dados financeiros."}), 500
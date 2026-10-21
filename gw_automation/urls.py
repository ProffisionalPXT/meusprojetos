"""URLs conhecidas do GW Webtrans (PURM)."""

BASE = "https://webtrans.saas.gwsistemas.com.br"

MENU = f"{BASE}/menu"
LOGIN = f"{BASE}/login"

# Consulta / cadastro de motoristas
CONSULTA_MOTORISTAS = f"{BASE}/ConsultaControlador?codTela=60"
NOVO_MOTORISTA = f"{BASE}/cadmotorista?acao=iniciar"

# Outros cadastros (quando abrir "Novo" a partir do vínculo)
NOVO_VEICULO = f"{BASE}/cadveiculo?acao=iniciar"
NOVO_PROPRIETARIO = f"{BASE}/cadproprietario?acao=iniciar"

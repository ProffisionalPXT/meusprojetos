"""
Leitor Ultrarrápido de Documentos (GW Motorista Bot).
Lê os arquivos de input/motorista, extrai CNH (com espelho), CRLVs (Cavalo/Carreta/Truck),
ANTT e endereço de residência, gerando dados_manuais.json instantaneamente.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Habilita cores no console Windows
if sys.platform == "win32":
    os.system("")

from dotenv import load_dotenv
load_dotenv(override=True)

# Configuração de alta velocidade
os.environ.setdefault("OCR_ENGINE", "auto")
os.environ.setdefault("CONFIRMAR_DADOS", "0")

from ocr.extrair_dados import extrair_dados_do_caso
from utils.paths import INPUT_DIR, garantir_pastas
from utils.receber_fotos import listar_casos
from ocr.models import DadosCaso


def ler_e_salvar_dados_rapido() -> DadosCaso:
    garantir_pastas()
    pasta_motorista = INPUT_DIR / "motorista"
    
    # Remove temporariamente o dados_manuais.json antigo para forçar releitura limpa dos PDFs atuais
    manual_file = pasta_motorista / "dados_manuais.json"
    if manual_file.exists():
        try:
            manual_file.unlink()
        except Exception:
            pass

    casos = listar_casos()
    if not casos:
        print("[!] Nenhum documento encontrado em input/motorista/")
        sys.exit(1)

    caso = casos[0]
    for c in casos:
        if c.nome.lower() == "motorista":
            caso = c
            break

    t0 = time.time()
    print(f"\n{'='*65}")
    print(f"  LEITURA ULTRARRAPIDA DE DOCUMENTOS - GW MOTORISTA BOT")
    print(f"{'='*65}")
    print(f"[*] Analisando {len(caso.arquivos)} arquivo(s) na pasta 'input/motorista'...")

    dados = extrair_dados_do_caso(caso)
    elapsed = time.time() - t0

    # Grava o dados_manuais.json no padrão exigido pelo robô
    saida = {
        "caso_nome": "motorista",
        "rntrc_tac": dados.rntrc_tac or "",
        "motorista": dados.motorista.to_dict() if hasattr(dados.motorista, "to_dict") else dados.motorista.__dict__,
        "veiculo": dados.veiculo.__dict__.copy() if dados.veiculo else None,
        "carreta": dados.carreta.__dict__.copy() if dados.carreta else None,
        "bitrem": dados.bitrem.__dict__.copy() if dados.bitrem else None,
        "tri_reboque": dados.tri_reboque.__dict__.copy() if dados.tri_reboque else None,
        "proprietario": dados.proprietario.__dict__.copy() if dados.proprietario else None,
    }
    
    if saida["veiculo"] and dados.veiculo and dados.veiculo.proprietario:
        saida["veiculo"]["proprietario"] = dados.veiculo.proprietario.__dict__.copy() if hasattr(dados.veiculo.proprietario, "__dict__") else dados.veiculo.proprietario
    if saida["carreta"] and dados.carreta and dados.carreta.proprietario:
        saida["carreta"]["proprietario"] = dados.carreta.proprietario.__dict__.copy() if hasattr(dados.carreta.proprietario, "__dict__") else dados.carreta.proprietario
    if saida["bitrem"] and dados.bitrem and dados.bitrem.proprietario:
        saida["bitrem"]["proprietario"] = dados.bitrem.proprietario.__dict__.copy() if hasattr(dados.bitrem.proprietario, "__dict__") else dados.bitrem.proprietario
    if saida["tri_reboque"] and dados.tri_reboque and dados.tri_reboque.proprietario:
        saida["tri_reboque"]["proprietario"] = dados.tri_reboque.proprietario.__dict__.copy() if hasattr(dados.tri_reboque.proprietario, "__dict__") else dados.tri_reboque.proprietario

    def _json_default(obj):
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)

    manual_file.write_text(json.dumps(saida, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")

    # Exibição do resumo formatado
    m = dados.motorista
    v = dados.veiculo
    c = dados.carreta
    
    print(f"\n[OK] Concluido em {elapsed:.2f}s com sucesso!\n")
    print("-" * 65)
    print(f" MOTORISTA: {m.nome} | CPF: {m.cpf} | RG: {m.rg} {m.orgao_emissor}")
    print(f" CNH: {m.cnh} | ESPELHO: {m.cnh_espelho} | CAT: {m.categoria_cnh} | VAL: {m.validade_cnh}")
    print(f" FILIACAO: Mae: {m.nome_mae} | Pai: {m.nome_pai}")
    print(f" ENDERECO: {m.endereco}, {m.bairro} - {m.cidade}/{m.uf} (CEP {m.cep})")
    print("-" * 65)
    if v:
        print(f" VEICULO ({v.tipo}): Placa: {v.placa} | Renavam: {v.renavam} | Mod: {v.marca_modelo_versao}")
        if v.proprietario:
            print(f"   Proprietario: {v.proprietario.nome} ({v.proprietario.cpf_cnpj})")
    if c:
        print(f" CARRETA: Placa: {c.placa} | Renavam: {c.renavam} | Mod: {c.marca_modelo_versao}")
        if c.proprietario:
            print(f"   Proprietario: {c.proprietario.nome} ({c.proprietario.cpf_cnpj})")
    if dados.rntrc_tac:
        print(f" ANTT / RNTRC: {dados.rntrc_tac}")
    print("-" * 65)
    print(f"[OK] Arquivo salvo com sucesso em: input/motorista/dados_manuais.json")
    print(f"[*] Agora basta dar dois cliques em 'INICIAR_ROBO.bat' para cadastrar!")
    print("=" * 65 + "\n")
    return dados


if __name__ == "__main__":
    ler_e_salvar_dados_rapido()

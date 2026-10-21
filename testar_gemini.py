"""
Teste só da leitura Gemini (sem abrir o GW).

Uso:
  1. Coloque fotos em input/<pasta>/
  2. GEMINI_API_KEY no .env
  3. python testar_gemini.py
"""
from dotenv import load_dotenv

load_dotenv()

from ocr.extrair_dados import extrair_dados_do_caso
from ocr.gemini_extrator import gemini_disponivel
from utils.receber_fotos import listar_casos, resumo_casos


def main() -> None:
    print("=== Teste Gemini (leitura de documentos) ===\n")
    if not gemini_disponivel():
        print("ERRO: GEMINI_API_KEY vazia no .env")
        print("1. Acesse https://aistudio.google.com/apikey")
        print("2. Crie uma chave")
        print("3. Cole em .env: GEMINI_API_KEY=AIza...")
        return

    casos = listar_casos()
    print(resumo_casos(casos))
    if not casos:
        print("\nColoque arquivos em input\\ e rode de novo.")
        return

    for caso in casos:
        print(f"\n--- {caso.nome} ---")
        dados = extrair_dados_do_caso(caso)
        print("\nJSON motorista:")
        for k, v in dados.motorista.to_dict().items():
            if v and k != "fotos":
                print(f"  {k}: {v}")
        if dados.veiculo:
            print("Veículo:", dados.veiculo.tipo, dados.veiculo.placa, dados.veiculo.marca)
        if dados.carreta:
            print("Carreta:", dados.carreta.tipo, dados.carreta.placa, dados.carreta.marca)
        if dados.proprietario:
            p = dados.proprietario
            print("Proprietário:", p.nome, p.cpf_cnpj, p.cidade, p.rntrc)


if __name__ == "__main__":
    main()

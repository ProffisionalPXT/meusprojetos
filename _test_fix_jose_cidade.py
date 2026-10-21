"""Testa correções de cidade/nome do caso JOSE."""
from ocr.parsers_locais import (
    parse_crlv,
    _limpa_nome,
    _cidade_parece_lixo,
)
from ocr.extrair_dados import (
    _cidade_extracao_lixo,
    _sanitizar_nome_pessoa,
    _mesclar_extracoes,
)
from ocr.tipos_documento import TipoDocumento


def main() -> None:
    t1 = """
CODIGO RENAVAM 00969456450
PLACA HHK5G06
MARCA SR/FACCHINI SRF CF
ESPECIE CARGA SEMI-REBOQUE
CHASSI 94BF154388R008398
COR BRANCA
CARROCERIA FECHADA
NOME
JOSE FERREIRA SANTOS
CPF / CNPJ 368.924.755-15
LOCAL
BARRA DOS COQUEIROS SE
DATA 26/02/2026
"""
    r = parse_crlv(t1)
    print("LIMPO:", r["cidade"], r["uf"], repr(r["proprietario_nome"]), r["placa"])
    assert r["cidade"] == "BARRA DOS COQUEIROS", r["cidade"]
    assert r["uf"] == "SE"
    assert r["proprietario_nome"] == "JOSE FERREIRA SANTOS"

    t2 = """
NOME
' JOSE FERREIRA SANTOS
CPF 368.924.755-15
LOCAL
BARRA DOS COQUEIROS SE
"""
    r2 = parse_crlv(t2)
    print("ASPAS:", repr(r2["proprietario_nome"]), r2["cidade"])
    assert "'" not in r2["proprietario_nome"], r2["proprietario_nome"]
    assert r2["cidade"] == "BARRA DOS COQUEIROS"

    t3 = """
NOME JOSE FERREIRA SANTOS
CPF 368.924.755-15
LOCAL NAL DRAT ALONE AINIVE DUTHAT SE
"""
    r3 = parse_crlv(t3)
    print("LIXO:", repr(r3["cidade"]), r3.get("uf"))
    assert not r3["cidade"] or r3["cidade"] == "BARRA DOS COQUEIROS"

    t4 = """
NOME JOSE FERREIRA SANTOS
CPF 368.924.755-15
LOCAL RARE SOE SE
COQUEIROS SE
"""
    r4 = parse_crlv(t4)
    print("COQUEIROS:", r4["cidade"], r4["uf"])
    assert r4["cidade"] == "BARRA DOS COQUEIROS"

    assert _limpa_nome("' JOSE FERREIRA SANTOS") == "JOSE FERREIRA SANTOS"
    assert _cidade_parece_lixo("NAL DRAT ALONE AINIVE DUTHAT")
    assert _cidade_parece_lixo("RARE SOE")
    assert not _cidade_parece_lixo("BARRA DOS COQUEIROS")
    assert _sanitizar_nome_pessoa("' JOSE FERREIRA SANTOS") == "JOSE FERREIRA SANTOS"
    assert _cidade_extracao_lixo("NAL DRAT ALONE AINIVE DUTHAT")

    local = {
        "crlv": [
            {
                "_arquivo": "a.jpg",
                "placa": "HHK5G06",
                "cidade": "NAL DRAT ALONE AINIVE DUTHAT",
                "uf": "SE",
                "proprietario_nome": "' JOSE FERREIRA SANTOS",
            }
        ]
    }
    gem = {
        "crlv": [
            {
                "_arquivo": "a.jpg",
                "cidade": "BARRA DOS COQUEIROS",
                "uf": "SE",
                "proprietario_nome": "JOSE FERREIRA SANTOS",
            }
        ]
    }
    for t in TipoDocumento:
        local.setdefault(t.value, [])
        gem.setdefault(t.value, [])
    m = _mesclar_extracoes(local, gem)
    ex = m["crlv"][0]
    print("MERGE:", ex["cidade"], repr(ex["proprietario_nome"]))
    assert ex["cidade"] == "BARRA DOS COQUEIROS"
    assert ex["proprietario_nome"] == "JOSE FERREIRA SANTOS"
    print("ALL OK")


if __name__ == "__main__":
    main()

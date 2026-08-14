"""
Busca CEP quando o bot sabe a cidade (ex.: naturalidade PAULISTA/PE)
mas não tem CEP no documento.

Fluxo desejado (usuário):
  1. Sabe que nasceu / mora em PAULISTA-PE
  2. "Procura CEP" da cidade (ViaCEP = equivalente prático ao Google "cep paulista pe")
  3. Preenche o campo CEP no form
  4. A cidade embaixo preenche sozinha (após lupa/blur do CEP no GW)

ViaCEP: https://viacep.com.br
Faixa Paulista/PE (Bing/Google): 53400-001 a 53499-999
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Optional, Tuple

from utils.endereco_fallback import buscar_endereco_regiao, EnderecoPadrao

# Faixas conhecidas (quando a API falha) - geradas a partir de buscas tipo "cep X uf"
_FAIXAS_CEP = {
    ("PAULISTA", "PE"): "53401000",  # faixa 53400–53499
    ("RECIFE", "PE"): "50010000",
    ("OLINDA", "PE"): "53010000",
    ("JABOATAO DOS GUARARAPES", "PE"): "54010000",
    ("ARAPIRACA", "AL"): "57300005",
    ("MACEIO", "AL"): "57020000",
    ("GOIANIA", "GO"): "74003010",
    ("CURITIBA", "PR"): "80010000",
    ("COLOMBO", "PR"): "83410000",
}


def _norm_cidade(s: str) -> str:
    import unicodedata

    s = (s or "").strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    for sep in (" - ", "/", ","):
        if sep in s:
            s = s.split(sep)[0]
    return " ".join(s.split())


def _http_get_json(url: str, timeout: float = 8.0):
    req = urllib.request.Request(url, headers={"User-Agent": "gw-motorista-bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def buscar_cep_viacep(cidade: str, uf: str, logradouro: str = "Centro") -> Optional[str]:
    """
    Consulta ViaCEP por UF + cidade (+ logradouro opcional).
    Ex.: PE + Paulista -> CEPs da faixa 534xx.
    """
    cidade_q = (cidade or "").strip()
    uf_q = (uf or "").strip().upper()
    if not cidade_q or len(uf_q) != 2:
        return None
    # tenta com logradouro e sem
    for log in (logradouro, "Rua", ""):
        try:
            if log:
                path = f"/ws/{uf_q}/{urllib.parse.quote(cidade_q)}/{urllib.parse.quote(log)}/json/"
            else:
                # sem logradouro a API exige 3 partes; usa "a" genérico
                path = f"/ws/{uf_q}/{urllib.parse.quote(cidade_q)}/a/json/"
            url = "https://viacep.com.br" + path
            print(f"[CEP] Consultando ViaCEP: {cidade_q}/{uf_q} ...")
            data = _http_get_json(url)
            if isinstance(data, dict) and data.get("erro"):
                continue
            if isinstance(data, list) and data:
                cep = (data[0].get("cep") or "").replace("-", "")
                if len(cep) == 8:
                    print(f"[CEP] ViaCEP encontrou: {cep} ({data[0].get('localidade')}/{data[0].get('uf')})")
                    return cep
            if isinstance(data, dict) and data.get("cep"):
                cep = data["cep"].replace("-", "")
                if len(cep) == 8:
                    print(f"[CEP] ViaCEP: {cep}")
                    return cep
        except Exception as e:
            print(f"[CEP] ViaCEP falhou ({log or 'sem log'}): {e}")
            continue
    return None


def buscar_cep_por_cidade(
    cidade: str = "",
    uf: str = "",
    naturalidade: str = "",
) -> Tuple[str, Optional[EnderecoPadrao]]:
    """
    Resolve CEP a partir da cidade/naturalidade.

    Returns:
        (cep_8_digitos, endereco_padrao_opcional)
    """
    # Prioridade: NATURALIDADE (nascimento) -> cidade explícita
    cid_nat = _norm_cidade(naturalidade)
    uf_n = (uf or "").strip().upper()

    # extrai UF da naturalidade "ARAPIRACA - AL" / "PAULISTA/PE"
    if naturalidade:
        parts = naturalidade.replace("/", " ").replace("-", " ").replace(",", " ").split()
        if parts and len(parts[-1]) == 2 and parts[-1].isalpha():
            uf_from_nat = parts[-1].upper()
            cid_from_nat = _norm_cidade(" ".join(parts[:-1]))
            if not uf_n:
                uf_n = uf_from_nat
            if cid_from_nat:
                cid_nat = cid_from_nat

    cid = cid_nat or _norm_cidade(cidade)

    if not cid:
        end = buscar_endereco_regiao(naturalidade=naturalidade)
        if end:
            return end.cep, end
        return "", None

    # 1) ViaCEP pela cidade de nascimento
    cep = buscar_cep_viacep(cid.title() if cid.isupper() else cid, uf_n or "PE")
    if cep:
        end = buscar_endereco_regiao(naturalidade=cid, cidade=cid, uf=uf_n)
        if not end:
            end = EnderecoPadrao(cid, uf_n or "PE", cep, "RUA DO COMERCIO", "CENTRO")
        return cep, end

    # 2) Faixa conhecida
    key = (cid, uf_n)
    if key in _FAIXAS_CEP:
        print(f"[CEP] Faixa conhecida {cid}/{uf_n} -> {_FAIXAS_CEP[key]}")
        return _FAIXAS_CEP[key], buscar_endereco_regiao(cidade=cid, uf=uf_n)

    # 3) Tabela local (naturalidade primeiro)
    end = buscar_endereco_regiao(cidade=cid, uf=uf_n, naturalidade=naturalidade or cid)
    if end:
        print(f"[CEP] Fallback local {end.cidade}/{end.uf} -> {end.cep}")
        return end.cep, end

    return "", None

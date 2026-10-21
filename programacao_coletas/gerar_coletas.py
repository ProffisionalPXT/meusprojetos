import os
import sys
import json
from playwright.sync_api import sync_playwright

def render_html(data):
    title = data.get("data", "PROGRAMAÇÃO DE COLETAS")
    if not title.startswith("PROGRAMAÇÃO DE COLETAS"):
        title = f"PROGRAMAÇÃO DE COLETAS DO DIA {title}"
        
    obs = data.get("obs", "").strip().upper()
    coletas = data.get("coletas", [])

    # Detecção automática de coletas múltiplas se tipo não for especificado
    driver_counts = {}
    for c in coletas:
        m = c.get("motorista", "").strip().upper()
        if m:
            driver_counts[m] = driver_counts.get(m, 0) + 1

    driver_seen = {}
    rows_html = []

    for c in coletas:
        m = c.get("motorista", "").strip().upper()
        tipo = c.get("tipo", "").strip().upper()
        
        if not tipo and m:
            if driver_counts.get(m, 0) > 1:
                driver_seen[m] = driver_seen.get(m, 0) + 1
                tipo = f"{driver_seen[m]}-COLETA"

        cliente = c.get("cliente", "").strip().upper()
        horario = c.get("horario", "").strip().upper()
        if horario and not horario.startswith("HOR:"):
            horario = f"HOR: {horario}"

        tag_div = f'<div class="d-tag">{tipo}</div>' if tipo else ''

        row = f"""
        <tr class="tbl-row">
          <td class="c-driver">
            <div class="d-name">{m}</div>
            {tag_div}
          </td>
          <td class="c-info">
            <div class="i-client">{cliente}</div>
            <div class="i-line"></div>
            <div class="i-time">{horario}</div>
          </td>
        </tr>
        """
        rows_html.append(row)

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>
  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    font-family: Arial, "Helvetica Neue", Helvetica, sans-serif;
  }}
  body {{
    background-color: #ffffff;
    display: flex;
    justify-content: flex-start;
    padding: 0;
  }}
  #capture-table {{
    width: 660px;
    background: #ffffff;
    border: 1.5px solid #222;
  }}
  .hdr-blue {{
    background-color: #4b82c2;
    color: #000000;
    font-size: 15.5px;
    font-weight: 900;
    padding: 11px 16px;
    letter-spacing: 0.3px;
    text-transform: uppercase;
  }}
  .bar-red {{
    display: flex;
    height: 14px;
    background-color: #e60000;
    border-top: 1.5px solid #222;
    border-bottom: 1.5px solid #222;
  }}
  .bar-red .b-col-left {{
    width: 180px;
    border-right: 1.5px solid #222;
  }}
  .bar-red .b-col-right {{
    flex: 1;
  }}
  .tbl-coletas {{
    width: 100%;
    border-collapse: collapse;
  }}
  .tbl-row {{
    border-bottom: 1.5px solid #333;
  }}
  .c-driver {{
    width: 180px;
    vertical-align: middle;
    text-align: center;
    padding: 9px 8px;
    border-right: 1.5px solid #333;
  }}
  .d-name {{
    font-size: 13.5px;
    font-weight: bold;
    color: #000;
    text-transform: uppercase;
  }}
  .d-tag {{
    font-size: 11px;
    font-weight: bold;
    color: #e60000;
    margin-top: 3px;
    text-transform: uppercase;
  }}
  .c-info {{
    vertical-align: middle;
    text-align: center;
    padding: 0;
  }}
  .i-client {{
    padding: 7px 10px 5px 10px;
    font-size: 12.5px;
    font-weight: bold;
    color: #000;
    text-transform: uppercase;
  }}
  .i-line {{
    border-top: 1px solid #777;
    margin: 0 10px;
  }}
  .i-time {{
    padding: 4px 10px 7px 10px;
    font-size: 11.5px;
    font-weight: bold;
    color: #e60000;
    text-transform: uppercase;
  }}
  .tbl-row-obs {{
    border-bottom: none;
  }}
  .c-obs-title {{
    width: 180px;
    vertical-align: middle;
    text-align: center;
    border-right: 1.5px solid #333;
    font-size: 13.5px;
    font-weight: 900;
    color: #e60000;
    padding: 10px 8px;
  }}
  .c-obs-text {{
    padding: 8px 12px;
    font-size: 9.8px;
    font-weight: bold;
    color: #e60000;
    line-height: 1.35;
    text-transform: uppercase;
    text-align: left;
  }}
</style>
</head>
<body>
  <div id="capture-table">
    <div class="hdr-blue">{title}</div>
    <div class="bar-red">
      <div class="b-col-left"></div>
      <div class="b-col-right"></div>
    </div>
    <table class="tbl-coletas">
      <tbody>
        {''.join(rows_html)}
      </tbody>
      <tfoot>
        <tr class="tbl-row tbl-row-obs">
          <td class="c-obs-title">OBS:</td>
          <td class="c-obs-text">{obs}</td>
        </tr>
      </tfoot>
    </table>
  </div>
</body>
</html>
"""
    return html_content

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "dados.json")
    
    if len(sys.argv) > 1:
        json_path = sys.argv[1]

    if not os.path.exists(json_path):
        print(f"Erro: Arquivo {json_path} não encontrado.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    html_code = render_html(data)
    temp_html = os.path.join(base_dir, "_temp_render.html")
    output_png = os.path.join(base_dir, "PROGRAMACAO_COLETAS.png")

    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_code)

    print("Renderizando imagem em alta resolução...")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2)
        page.goto("file:///" + temp_html.replace("\\", "/"))
        element = page.locator("#capture-table")
        element.screenshot(path=output_png)
        browser.close()

    try:
        os.remove(temp_html)
    except:
        pass

    print(f"[SUCESSO] Imagem gerada com exito: {output_png}")
    try:
        os.startfile(output_png)
    except:
        pass

if __name__ == "__main__":
    main()

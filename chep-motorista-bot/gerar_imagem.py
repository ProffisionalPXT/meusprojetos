import asyncio
from playwright.async_api import async_playwright

html_content = """
<!DOCTYPE html>
<html>
<head>
<style>
  body {
    font-family: Arial, sans-serif;
    margin: 20px;
    background: white;
  }
  table {
    border-collapse: collapse;
    width: 600px;
    border: 1px solid black;
  }
  th, td {
    border: 1px solid black;
    padding: 10px;
  }
  th {
    background-color: red;
    color: black;
    text-align: left;
    font-size: 14px;
    font-weight: bold;
    padding: 5px 10px;
  }
  .driver-col {
    width: 30%;
    font-weight: bold;
    text-transform: uppercase;
    font-size: 12px;
  }
  .dest-col {
    width: 70%;
  }
  .dest-name {
    font-weight: bold;
    font-size: 12px;
    text-transform: uppercase;
  }
  .time {
    color: red;
    font-size: 11px;
    font-weight: bold;
    margin-top: 5px;
    text-transform: uppercase;
    text-align: center;
  }
  .dest-container {
    display: flex;
    flex-direction: column;
    align-items: center;
  }
</style>
</head>
<body>
  <table>
    <tr>
      <th colspan="2">MOTORISTA</th>
    </tr>
    <tr>
      <td class="driver-col">WILSON REIS</td>
      <td class="dest-col">
        <div class="dest-container">
            <span class="dest-name">YOKI 448 PALLETES</span>
            <span class="time">HOR: 08 AS 13:00</span>
        </div>
      </td>
    </tr>
    <tr>
    <tr>
      <td class="driver-col">WILSON REIS</td>
      <td class="dest-col">
        <div class="dest-container">
            <span class="dest-name">DECMINAS DISTRIBUIDORA 276 PALLETES</span>
            <span class="time">HOR: 08:00</span>
        </div>
      </td>
    </tr>
    <tr>
      <td class="driver-col">WILSON REIS</td>
      <td class="dest-col">
        <div class="dest-container">
            <span class="dest-name">CENCOSUD BR COMERCIAL 223 PALLETES</span>
            <span class="time">HOR: 09:00</span>
        </div>
      </td>
    </tr>
  </table>
</body>
</html>
"""

async def main():
    with open('tabela_temp.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        # file:// url needs absolute path properly formatted, but we can just use file:///
        import os
        path = 'file:///' + os.path.abspath('tabela_temp.html').replace('\\', '/')
        await page.goto(path)
        
        # Obter o bounding box da tabela para tirar o print só dela
        table = page.locator('table')
        await table.screenshot(path='teste_programacao.png')
        
        await browser.close()
        
    print("Imagem gerada: teste_programacao.png")

if __name__ == '__main__':
    asyncio.run(main())

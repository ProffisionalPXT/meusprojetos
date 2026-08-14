# Mapeamento de Clientes e Endereços (De/Para)

Este arquivo serve como "cérebro" para o robô ou para o prompt do Gemini na hora de traduzir o que vem na imagem do WhatsApp para o que está no sistema CHEP.

## Nomes e Razões Sociais
* **ASSAI** -> `SENDAS` ou `Sendas Distribuidora S/A`
* **WMS MAX ATACADO** ou **WMS** -> `WMS SUPERMERCADOS DO BRASIL LTDA.`
* **COCA COLA** -> `NORSA`

## Bairros/Locais para Nomes de Ruas (Para checagem no Sub-frame)
Quando o sistema tiver múltiplos registros genéricos (ex: várias Sendas ou WMS), o robô deve clicar na linha, ler o `Endereço de origem` na tabela inferior e buscar pelas palavras-chave da rua correspondente ao bairro:

* **Paralela** -> `Avenida Luis Viana`
* **Paripe / Lobato** -> `Avenida Afrânio Peixoto`
* **Bonocô** -> `Avenida Mario Leal`
* **Cabula** -> `Rua Silveira Martins`
* **Barradão** -> `Avenida Maria Lúcia`
* **Canabrava** -> `Rua Castro Valente`
* **Barros Reis** -> `Avenida Barros Reis`
* **Salete** -> `Rua do Salete`
* **Iguatemi** -> `Avenida Santiago de Compostela`
* **Baixa de quinta** -> `Rua Genaro de Carvalho`
* **Cajazeiras** (1) -> `Rua Vereador Zezeu`
* **Calçada** (1) -> `Rua Elias Nazaré`
* **Caminho de areia** -> `Avenida Caminho de Areia`
* **Simoes Filho** -> `Avenida Eng Walter Aragão`
* **San Martin** -> `Avenida Gen. San Martin`
* **Nilo Picanha** -> `Rua Nilo Picanha`
* **Calçada** (2) -> `Avenida Jequitaia`
* **Camaçari / Estrada do coco** -> `Lagoa branca`
* **Pirajá** -> `Rua Oito de novembro`
* **São Caetano** -> `Estrada de campinas`
* **Pau de lima** (Geral) -> `Rua Ismar araujo`
* **Itacimirim** -> `Camaçari rod do coco`
* **Pau de lima** (Quando for WMSMAX) -> `Rua Pastor José Guilherme`
* **Mata escura** -> `Avenida Cardeal Avelar Brandão`
* **AGM / Rotula do abacaxi** -> `Av antonio Carlos Magalhaes`
* **Periperi** -> `Rua Frederico Costa`
* **Uruguai** -> `Rua Luis regis Pacheco`
* **Amarelina** -> `Rua Janio quadros`
* **Cajazeiras** (2) -> `Rua Coqueiro grande`
* **Pernambuês** -> `Av Tancredo neves`
* **Vasco da Gama** -> `Av Vasco da Gama`
* **Piatã** -> `Av Octavio Mangabeira`
* **São Cristovão** -> `Av. São Cristovão`
* **Mussuranga** -> `Rua Prof Plinio Garcez`
* **Paripe** (2) -> `Av. V bronze`
* **Ogujá** -> `Avenida General Graça lessa`
* **Barreiras** -> `Av estradas das barreiras`

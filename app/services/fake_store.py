from __future__ import annotations

import httpx

from ..config import FAKE_STORE_URL


DESCRIPTIONS_PT_BR = {
    1: "Mochila ideal para o uso diário e para caminhadas. Possui compartimento acolchoado para notebook de até 15 polegadas e espaço para seus itens essenciais.",
    2: "Camiseta masculina leve e macia, com modelagem ajustada, mangas raglan contrastantes e gola Henley com três botões. Oferece conforto, respirabilidade e boa durabilidade para o uso casual.",
    3: "Jaqueta masculina de algodão indicada para primavera, outono e inverno. Uma opção versátil para trabalho, trilhas, acampamentos, ciclismo, viagens e outras atividades ao ar livre.",
    4: "Peça masculina casual com modelagem slim. A cor pode variar ligeiramente conforme a tela. Consulte as medidas detalhadas antes de escolher o tamanho.",
    5: "Pulseira da coleção Legends inspirada no Naga, o mítico dragão das águas que protege a pérola do oceano. Use voltada para dentro como símbolo de amor e abundância ou para fora como proteção.",
    6: "Joia delicada com acabamento em ouro e micropavê. Produto vendido com garantia de satisfação e possibilidade de devolução ou troca em até 30 dias.",
    7: "Anel clássico com banho de ouro branco e pedra solitária, ideal para noivado, casamento, aniversário ou outras ocasiões especiais.",
    8: "Brincos alargadores com acabamento em ouro rosé e formato duplo. Produzidos em aço inoxidável 316L para maior resistência e durabilidade.",
    9: "HD externo portátil de 2 TB com compatibilidade USB 3.0 e USB 2.0, transferência rápida de dados e alta capacidade. Formatado em NTFS para Windows; outros sistemas podem exigir reformatação.",
    10: "SSD interno de 1 TB que acelera inicialização, desligamento e carregamento de aplicativos. Oferece equilíbrio entre desempenho e confiabilidade, com velocidades de leitura de até 535 MB/s e gravação de até 450 MB/s.",
    11: "SSD de 256 GB com memória 3D NAND e cache SLC, desenvolvido para inicialização rápida e melhor desempenho do sistema. O formato fino de 7 mm é adequado para ultrabooks e notebooks compactos.",
    12: "HD externo portátil de 4 TB para expandir o armazenamento do PlayStation 4. Tem configuração simples, design compacto, alta capacidade e garantia limitada de três anos do fabricante.",
    13: "Monitor IPS ultrafino de 21,5 polegadas com resolução Full HD, taxa de atualização de 75 Hz e tempo de resposta de 4 ms. Conta com design sem bordas e tecnologia Radeon FreeSync.",
    14: "Monitor gamer curvo super ultrawide de 49 polegadas, proporção 32:9, tecnologia QLED e suporte a HDR. A taxa de 144 Hz e o tempo de resposta de 1 ms reduzem borrões e atrasos nos jogos.",
    15: "Jaqueta feminina 3 em 1 para neve e inverno, com forro de fleece removível, capuz ajustável e bolsos com zíper. As camadas podem ser usadas juntas ou separadas conforme o clima.",
    16: "Jaqueta feminina estilo motociclista em couro sintético, com capuz removível e forro confortável. Possui bolsos frontais, detalhes na cintura e costuras laterais. Recomenda-se lavagem à mão.",
    17: "Capa de chuva feminina leve, indicada para viagens e uso casual. Possui capuz e cintura ajustáveis, fechamento por botões e zíper, forro listrado e dois bolsos laterais.",
    18: "Blusa feminina de manga curta, feita com 95% viscose e 5% elastano. O tecido é leve, confortável e elástico, com acabamento canelado nas mangas e no decote.",
    19: "Camiseta feminina leve e respirável, feita em poliéster com tecnologia que ajuda a afastar a umidade. Possui gola em V confortável e modelagem mais ajustada.",
    20: "Camiseta feminina casual de algodão com elastano, manga curta, estampa e gola em V. O tecido é macio e flexível, adequado para trabalho, escola, praia e uso diário em todas as estações.",
}


def localized_description(external_id: int, fallback: str | None) -> str:
    return DESCRIPTIONS_PT_BR.get(
        external_id, fallback or "Produto importado do catálogo externo."
    )


class FakeStoreUnavailable(RuntimeError):
    pass


async def fetch_products() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{FAKE_STORE_URL}/products")
            response.raise_for_status()
            products = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise FakeStoreUnavailable("Não foi possível consultar o catálogo externo.") from error

    normalized = []
    for item in products:
        rating = item.get("rating") or {}
        external_id = int(item["id"])
        normalized.append(
            {
                "external_id": external_id,
                "title": item["title"],
                "description": localized_description(
                    external_id, item.get("description")
                ),
                "price": float(item["price"]),
                "category": item.get("category") or "Outros",
                "image": item["image"],
                "stock": max(3, int(rating.get("count", 10)) % 31),
                "rating": float(rating.get("rate", 0)),
                "rating_count": int(rating.get("count", 0)),
            }
        )
    return normalized

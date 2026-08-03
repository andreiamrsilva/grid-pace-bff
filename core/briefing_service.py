import logging
from typing import Optional, Dict, Any
from datetime import date
from models.event_briefing import EventBriefing, WeatherBriefing
from core.weather_service import fetch_event_weather_briefing
from core.database_service import get_event_by_id_from_db
from core.redis_service import get_cached_data, set_cached_data

logger = logging.getLogger(__name__)

# --- Curated Motorsport Briefing Database ---

BRIEFING_CATALOG: Dict[str, Dict[str, Any]] = {
    # F1 Circuits
    "f1_monaco": {
        "name": "Circuit de Monaco",
        "city": "Monte Carlo",
        "country": "Monaco",
        "latitude": 43.7347,
        "longitude": 7.4206,
        "surface_type": "Asfalto (Circuito de Rua)",
        "total_distance_km": 260.286,
        "laps_count": 78,
        "tactical_briefing": "O GP de Mónaco é a prova mais exigente em termos de precisão técnica e qualificação. "
                            "Devido à extrema dificuldade de ultrapassagem nas ruas estreitas, a posição de partida "
                            "e a estratégia de pit stop sob Safety Car são determinantes. A degradação de pneus é baixa, "
                            "mas a margem de erro nos raios das curvas é zero.",
        "last_winner": "Charles Leclerc (Ferrari)",
        "event_record": "1:12.909 - Lewis Hamilton (2021)",
        "track_map_url": "https://media.formula1.com/image/upload/v1677244985/content/dam/fom-website/2018-redesign-assets/Circuit%20maps%2016x9/Monaco_Circuit.png",
    },
    "f1_silverstone": {
        "name": "Silverstone Circuit",
        "city": "Silverstone",
        "country": "Reino Unido",
        "latitude": 52.0786,
        "longitude": -1.0169,
        "surface_type": "Asfalto (Alta Aderência / Alta Velocidade)",
        "total_distance_km": 306.198,
        "laps_count": 52,
        "tactical_briefing": "Circuito ultrarrápido com sequências icónicas como Maggotts, Becketts e Chapel. "
                            "Impõe altíssima carga lateral nos pneus (especialmente dianteiro esquerdo), tornando o "
                            "gestão de borracha e acerto de alta pressão aerodinâmica cruciais. Ventos cruzados e chuvas "
                            "súbitas costumam alterar drasticamente a aderência.",
        "last_winner": "Lewis Hamilton (Mercedes)",
        "event_record": "1:27.097 - Max Verstappen (2020)",
        "track_map_url": "https://media.formula1.com/image/upload/v1677244985/content/dam/fom-website/2018-redesign-assets/Circuit%20maps%2016x9/Great_Britain_Circuit.png",
    },
    "f1_spa": {
        "name": "Circuit de Spa-Francorchamps",
        "city": "Stavelot",
        "country": "Bélgica",
        "latitude": 50.4372,
        "longitude": 5.9714,
        "surface_type": "Asfalto (Circuito Misto de Montanha)",
        "total_distance_km": 308.052,
        "laps_count": 44,
        "tactical_briefing": "O circuito mais longo do calendário. Requer um compromisso aerodinâmico entre "
                            "alta velocidade de ponta no Setor 1/3 (reta de Kemmel) e apoio na secção sinuosa do Setor 2. "
                            "O clima nas Ardenas é notoriamente imprevisível, sendo comum chover num setor e estar seco noutro.",
        "last_winner": "Lewis Hamilton (Mercedes)",
        "event_record": "1:46.286 - Valtteri Bottas (2018)",
        "track_map_url": "https://media.formula1.com/image/upload/v1677244985/content/dam/fom-website/2018-redesign-assets/Circuit%20maps%2016x9/Belgium_Circuit.png",
    },
    "f1_monza": {
        "name": "Autodromo Nazionale Monza",
        "city": "Monza",
        "country": "Itália",
        "latitude": 45.6156,
        "longitude": 9.2811,
        "surface_type": "Asfalto (Templo da Velocidade)",
        "total_distance_km": 306.720,
        "laps_count": 53,
        "tactical_briefing": "Configuração de mínima carga aerodinâmica (low downforce) para maximizar a velocidade máxima nas retas. "
                            "As travagens violentas para as chicanes (Prima Variante e Ascari) exigem estabilidade extrema nas travagens e boa tração à saída.",
        "last_winner": "Charles Leclerc (Ferrari)",
        "event_record": "1:21.046 - Rubens Barrichello (2004)",
        "track_map_url": "https://media.formula1.com/image/upload/v1677244985/content/dam/fom-website/2018-redesign-assets/Circuit%20maps%2016x9/Italy_Circuit.png",
    },
    "f1_interlagos": {
        "name": "Autódromo José Carlos Pace",
        "city": "São Paulo",
        "country": "Brasil",
        "latitude": -23.7036,
        "longitude": -46.6997,
        "surface_type": "Asfalto (Circuito Anti-horário)",
        "total_distance_km": 305.909,
        "laps_count": 71,
        "tactical_briefing": "Layout fluido em sentido anti-horário com acentuadas variações de relevo e excelentes oportunidades de ultrapassagem no S do Senna. "
                            "As condições meteorológicas em São Paulo são frequentemente instáveis, gerando corridas caóticas e cheias de alternâncias.",
        "last_winner": "Max Verstappen (Red Bull Racing)",
        "event_record": "1:10.540 - Valtteri Bottas (2018)",
        "track_map_url": "https://media.formula1.com/image/upload/v1677244985/content/dam/fom-website/2018-redesign-assets/Circuit%20maps%2016x9/Brazil_Circuit.png",
    },

    # WRC Events
    "wrc_montecarlo": {
        "name": "Rallye Monte-Carlo",
        "city": "Gap / Monaco",
        "country": "Mónaco / França",
        "latitude": 44.5596,
        "longitude": 6.0798,
        "surface_type": "Misto (Asfalto, Gelo e Neve)",
        "total_distance_km": 324.44,
        "tactical_briefing": "O rali mais imprevisível do campeonato. A escolha de pneus (slicks, pneus de neve com ou sem cravos) "
                            "em troços com asfalto seco no vale e gelo negro no topo dos passos de montanha como Col de Turini é o fator chave para a vitória. "
                            "A leitura das equipas de batedores (gravel crews) é crucial.",
        "last_winner": "Thierry Neuville (Hyundai Shell Mobis WRT)",
        "event_record": "Sébastien Ogier - 9 Vitórias",
        "track_map_url": "https://www.wrc.com/cws/images/wrc_maps_montecarlo.png",
    },
    "wrc_portugal": {
        "name": "Vodafone Rally de Portugal",
        "city": "Matosinhos / Porto",
        "country": "Portugal",
        "latitude": 41.1822,
        "longitude": -8.6908,
        "surface_type": "Terra (Gravel arenoso e abrasivo)",
        "total_distance_km": 337.04,
        "tactical_briefing": "Troços técnicos em terra no norte e centro de Portugal (Lousã, Arganil, Fafe). "
                            "Na primeira passagem a pista tem gravilha solta beneficiando quem parte atrás; na segunda passagem sobem as pedras e pedregulhos soltos, "
                            "exigindo gestão dos pneus e proteção mecânica da suspensão. O salto de Fafe é o momento apogeu.",
        "last_winner": "Sébastien Ogier (Toyota Gazoo Racing WRT)",
        "event_record": "Sébastien Ogier - 6 Vitórias",
        "track_map_url": "https://www.wrc.com/cws/images/wrc_maps_portugal.png",
    },
    "wrc_finland": {
        "name": "Secto Rally Finland",
        "city": "Jyväskylä",
        "country": "Finlândia",
        "latitude": 62.2426,
        "longitude": 25.7473,
        "surface_type": "Terra Rápida (Gravel compacto com grandes saltos)",
        "total_distance_km": 305.69,
        "tactical_briefing": "Conhecido como a 'Grande Corrida de Gran Prix em Terra'. Média de velocidades impressionante com cristas cegas e saltos gigantescos (ex: Ouninpohja). "
                            "A precisão nas notas de ritmo (pacenotes) é vital: um carro desalinhado ao descolar do salto pode resultar numa saída violenta.",
        "last_winner": "Sébastien Ogier (Toyota Gazoo Racing WRT)",
        "event_record": "Marcus Grönholm - 7 Vitórias",
        "track_map_url": "https://www.wrc.com/cws/images/wrc_maps_finland.png",
    },
    "wrc_safari": {
        "name": "Safari Rally Kenya",
        "city": "Naivasha",
        "country": "Quénia",
        "latitude": -0.7172,
        "longitude": 36.4310,
        "surface_type": "Terra Exterminadora (Fesh-fesh, lama e pedras cortantes)",
        "total_distance_km": 367.76,
        "tactical_briefing": "O teste derradeiro de resistência física e mecânica. O terreno alterna entre poeira ultrafina (fesh-fesh) que sufoca motores, "
                            "rochas gigantes e valas profundas. As tempestades tropicais podem transformar troços secos num lamaçal impraticável em minutos.",
        "last_winner": "Kalle Rovanperä (Toyota Gazoo Racing WRT)",
        "event_record": "Shekhar Mehta / Sébastien Ogier - 5 Vitórias",
        "track_map_url": "https://www.wrc.com/cws/images/wrc_maps_kenya.png",
    },
    "wrc_acropolis": {
        "name": "EKO Acropolis Rally Greece",
        "city": "Lamia",
        "country": "Grécia",
        "latitude": 38.8959,
        "longitude": 22.4347,
        "surface_type": "Terra Rochosa (Temperaturas extremas e pedras soltas)",
        "total_distance_km": 305.30,
        "tactical_briefing": "O 'Rali dos Deuses'. Piso composto por pedras pontiagudas e calor sufocante na cabine. "
                            "A chave não é apenas andar rápido, mas preservar o carro, amortecedores e carcaça dos pneus contra furos graves.",
        "last_winner": "Thierry Neuville (Hyundai Shell Mobis WRT)",
        "event_record": "Colin McRae - 5 Vitórias",
        "track_map_url": "https://www.wrc.com/cws/images/wrc_maps_acropolis.png",
    }
}

def _match_catalog_entry(category: str, event_name: str, country: str) -> Optional[Dict[str, Any]]:
    """Helper to find the best matching briefing entry in our catalog."""
    cat_lower = category.lower()
    name_lower = event_name.lower() if event_name else ""
    country_lower = country.lower() if country else ""

    for key, data in BRIEFING_CATALOG.items():
        if cat_lower in key:
            if data["country"].lower() in country_lower or country_lower in data["country"].lower():
                return data
            if data["name"].lower() in name_lower or name_lower in data["name"].lower():
                return data
            if data["city"].lower() in name_lower or data["city"].lower() in country_lower:
                return data
    return None

async def get_event_briefing(category: str, event_id: int) -> EventBriefing:
    """
    Retrieves complete briefing for an event including circuit info, tactical analysis, records, and weather forecast.
    """
    category_upper = category.upper()
    cache_key = f"briefing:{category_upper.lower()}:{event_id}"
    
    # 1. Try Redis cache
    cached = await get_cached_data(cache_key)
    if cached:
        logger.debug(f"Redis HIT for event briefing: {cache_key}")
        return EventBriefing(**cached)

    # 2. Fetch event metadata from DB
    event = await get_event_by_id_from_db(event_id)
    
    event_name = event.name if event else f"{category_upper} Event #{event_id}"
    country = event.country if event else ""
    country_img = event.country_image_url if event else None
    start_date = event.start_date if event else date.today()
    finish_date = event.finish_date if event else date.today()

    # 3. Match against curated briefing catalog
    catalog_match = _match_catalog_entry(category_upper, event_name, country)

    if catalog_match:
        name = catalog_match.get("name", event_name)
        city = catalog_match.get("city", country)
        latitude = catalog_match.get("latitude", 0.0)
        longitude = catalog_match.get("longitude", 0.0)
        surface_type = catalog_match.get("surface_type", "Asfalto" if category_upper == "F1" else "Terra")
        total_distance_km = catalog_match.get("total_distance_km")
        laps_count = catalog_match.get("laps_count") if category_upper == "F1" else None
        tactical_briefing = catalog_match.get("tactical_briefing", "")
        last_winner = catalog_match.get("last_winner")
        event_record = catalog_match.get("event_record")
        track_map_url = catalog_match.get("track_map_url")
    else:
        # Generic fallback if not in curated catalog
        name = event_name if category_upper == "WRC" else f"Circuito de {country or event_name}"
        city = country or "Desconhecido"
        latitude = 45.0
        longitude = 9.0
        surface_type = "Asfalto" if category_upper == "F1" else "Terra (Misto)"
        total_distance_km = 305.0 if category_upper == "F1" else 320.0
        laps_count = 55 if category_upper == "F1" else None
        tactical_briefing = (
            f"Análise tática para o {event_name}. Preparação focada na afinação aerodinâmica, "
            f"estratégia de gestão de pneus e adaptação rápida às condições do piso e meteorologia local."
        )
        last_winner = None
        event_record = None
        track_map_url = None

    # 4. Fetch First Stage/Session details
    first_stage_name: Optional[str] = None
    first_stage_start_time: Optional[datetime] = None
    first_stage_location: Optional[str] = f"{city}, {country}".strip(", ")

    try:
        from core.database_service import get_stages_from_db
        stages = await get_stages_from_db(event_id)
        if not stages:
            if category_upper == "WRC":
                from ingestion.wrc_client import fetch_wrc_event_stages
                stages = await fetch_wrc_event_stages(event_id)
            elif category_upper == "F1":
                from ingestion.openf1_client import get_f1_event_sessions
                stages = await get_f1_event_sessions(event_id)
        
        if stages and len(stages) > 0:
            first_stage = stages[0]
            first_stage_name = first_stage.name
            first_stage_start_time = first_stage.start_time
    except Exception as e:
        logger.warning(f"Could not retrieve first stage for event {event_id}: {e}")

    # 5. Fetch Weather Briefing
    weather_briefing: Optional[WeatherBriefing] = None
    if latitude != 0.0 or longitude != 0.0:
        weather_briefing = await fetch_event_weather_briefing(
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            finish_date=finish_date
        )

    briefing_res = EventBriefing(
        event_id=event_id,
        category=category_upper,
        name=name,
        event_title=f"{event_name} {start_date.year if start_date else ''}".strip(),
        city=city,
        country=country or city,
        country_image_url=country_img,
        start_date=start_date,
        finish_date=finish_date,
        first_stage_name=first_stage_name,
        first_stage_start_time=first_stage_start_time,
        first_stage_location=first_stage_location,
        surface_type=surface_type,
        total_distance_km=total_distance_km,
        laps_count=laps_count,
        tactical_briefing=tactical_briefing,
        last_winner=last_winner,
        event_record=event_record,
        track_map_url=track_map_url,
        weather=weather_briefing
    )

    # Cache response in Redis for 1 hour (3600s)
    await set_cached_data(cache_key, briefing_res.model_dump(mode='json'), expiration_seconds=3600)

    return briefing_res

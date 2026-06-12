from typing import Optional
import pycountry

def get_logo_path(name: str) -> Optional[str]:
    """
    Returns a local logo file path based on a team or manufacturer name.
    The path will be relative to the /static/logos/ directory.
    """
    if not name:
        return None
    
    # A unified map for all categories
    logo_map = {
        # WRC
        "toyota": "toyota.png",
        "hyundai": "hyundai.png",
        "m-sport": "ford.png",
        "ford": "ford.png",
        "skoda": "skoda.png",
        "škoda": "skoda.png",
        "citroen": "citroen.png",
        "citroën": "citroen.png",
        "lancia": "lancia.png",
        
        # F1
        "red bull": "red_bull.png",
        "mercedes": "mercedes.png",
        "ferrari": "ferrari.png",
        "mclaren": "mclaren.png",
        "aston martin": "aston_martin.png",
        "alpine": "alpine.png",
        "williams": "williams.png",
        "rb": "rb.png",
        "sauber": "sauber.png",
        "haas": "haas.png",
        "alfa romeo": "alfa_romeo.png",
        "alphatauri": "alphatauri.png",
        "renault": "renault.png"
    }
    
    lower_name = name.lower()
    
    for key, filename in logo_map.items():
        if key in lower_name:
            return f"/logos/{filename}" # The path that the frontend will use
            
    return None

def get_country_iso_code(country_name: str) -> Optional[str]:
    """
    Finds the 2-letter ISO code for a given country name.
    Handles common mismatches between fastf1 and pycountry.
    """
    if not country_name:
        return None

    # Manual mapping for common mismatches
    country_map = {
        "UK": "GB",
        "USA": "US",
        "UAE": "AE",
        "Russia": "RU",
        "Korea": "KR"
    }

    if country_name in country_map:
        return country_map[country_name]

    try:
        country = pycountry.countries.get(name=country_name)
        if country:
            return country.alpha_2
        
        # If direct match fails, try a fuzzy search
        country = pycountry.countries.search_fuzzy(country_name)
        if country:
            return country[0].alpha_2
            
    except Exception:
        return None

    return None

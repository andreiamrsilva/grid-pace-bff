from typing import Optional

def get_manufacturer_logo_url(manufacturer_name: str) -> Optional[str]:
    """
    Constructs a URL for the manufacturer's logo based on its name.
    Uses the cdn.statustas.com service.
    """
    if not manufacturer_name:
        return None
    
    # Mapping for known manufacturers to match statustas.com names
    # The key is the string to search for, the value is the name in the URL
    manufacturer_map = {
        "toyota": "toyota",
        "hyundai": "hyundai",
        "m-sport": "ford", # M-Sport runs Ford cars
        "ford": "ford",
        "skoda": "skoda",
        "škoda": "skoda", # Handling special characters
        "citroen": "citroen",
        "citroën": "citroen", # Handling special characters
        "lancia": "lancia",
        "renault": "renault"
    }
    
    lower_name = manufacturer_name.lower()
    logo_name = None
    
    for key, value in manufacturer_map.items():
        if key in lower_name:
            logo_name = value
            break
            
    # If no match is found in our map, we don't attempt a fallback
    # to avoid generating broken URLs.
    if not logo_name:
        return None
    
    return f"https://cdn.statusas.com/ManufacturerIcons/32/{logo_name}.png"

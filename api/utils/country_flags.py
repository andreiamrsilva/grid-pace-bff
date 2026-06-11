def get_flag_url(iso2_code: str | None) -> str | None:
    """
    Generates a URL for the country flag based on the ISO 3166-1 alpha-2 code.
    Uses the free FlagCDN service.
    
    Args:
        iso2_code: The 2-letter country code (e.g., 'PT', 'FR').
        
    Returns:
        The URL of the flag image, or None if the code is invalid.
    """
    if not iso2_code or len(iso2_code) != 2:
        return None
        
    # FlagCDN expects lowercase ISO codes
    clean_code = iso2_code.strip().lower()
    return f"https://flagcdn.com/w320/{clean_code}.png"

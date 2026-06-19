import os

replacements = [
    ("core.database_service", "core.database_service"),
    ("ingestion.wrc_client", "ingestion.wrc_client"),
    ("ingestion.openf1_client", "ingestion.openf1_client"),
    ("core.redis_service", "core.redis_service"),
    ("core.config", "core.config"),
    ("core.utils", "core.utils"),
    ("ingestion.service", "ingestion.service")
]

for root, _, files in os.walk("."):
    for file in files:
        if file.endswith(".py") and "venv" not in root and ".ai" not in root:
            filepath = os.path.join(root, file)
            with open(filepath, "r") as f:
                content = f.read()
            
            new_content = content
            for old, new in replacements:
                new_content = new_content.replace(old, new)
            
            if new_content != content:
                with open(filepath, "w") as f:
                    f.write(new_content)
                print(f"Updated {filepath}")

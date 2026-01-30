from config import settings
print(f"API_KEYS type: {type(settings.API_KEYS)}")
print(f"API_KEYS value: {settings.API_KEYS}")
if settings.API_KEYS:
    print(f"First key type: {type(settings.API_KEYS[0])}")
    print(f"First key value: {settings.API_KEYS[0]}")

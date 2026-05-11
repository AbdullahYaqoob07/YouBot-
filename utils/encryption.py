import os
import json
import base64
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from loguru import logger
from config import settings

class EncryptionManager:
    _instance = None
    
    def __init__(self):
        """Initialize encryption key. Generates a safe fallback for local DEV."""
        # Try to load deterministic key from env
        key_str = getattr(settings, "ENCRYPTION_KEY", None)
        
        if key_str:
            try:
                self.key = key_str.encode()
                # Ensure it's a valid Fernet key length
                Fernet(self.key) 
            except ValueError:
                logger.warning("ENCRYPTION_KEY in settings is invalid format for Fernet. Generating fallback.")
                self.key = Fernet.generate_key()
        else:
            if not settings.DEBUG:
                logger.error("CRITICAL: No ENCRYPTION_KEY provided in production environment!")
            self.key = Fernet.generate_key()
            logger.warning(f"DEV fallback encryption key generated: {self.key.decode()}. Data will not survive restarts.")
            
        self.fernet = Fernet(self.key)

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

def encrypt_dict(data: dict) -> str:
    """Serialize a dictionary to JSON and encrypt it symmetrically."""
    if not data:
        return ""
    try:
        json_str = json.dumps(data)
        manager = EncryptionManager.get_instance()
        encrypted = manager.fernet.encrypt(json_str.encode("utf-8"))
        return encrypted.decode("utf-8")
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise ValueError("Failed to encrypt data")

def decrypt_dict(encrypted_str: str) -> dict:
    """Decrypt a symmetrically encrypted string back to a JSON dictionary."""
    if not encrypted_str:
        return {}
    try:
        manager = EncryptionManager.get_instance()
        decrypted_bytes = manager.fernet.decrypt(encrypted_str.encode("utf-8"))
        return json.loads(decrypted_bytes.decode("utf-8"))
    except Exception as e:
        logger.error(f"Decryption failed. Ensure ENCRYPTION_KEY matches. Error: {e}")
        return {}

def encrypt_string(cleartext: str) -> str:
    """Encrypt a raw string."""
    if not cleartext:
        return ""
    try:
        manager = EncryptionManager.get_instance()
        encrypted = manager.fernet.encrypt(cleartext.encode("utf-8"))
        return encrypted.decode("utf-8")
    except Exception as e:
        logger.error(f"String encryption failed: {e}")
        raise ValueError("Failed to encrypt string")

def decrypt_string(encrypted_str: str) -> str:
    """Decrypt a raw string."""
    if not encrypted_str:
        return ""
    try:
        manager = EncryptionManager.get_instance()
        decrypted_bytes = manager.fernet.decrypt(encrypted_str.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"String decryption failed: {e}")
        return ""

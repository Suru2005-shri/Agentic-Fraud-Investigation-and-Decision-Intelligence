"""Compatibility wrapper: ARGUS now seeds from the real HHG dataset."""
from .real_data import ensure_seeded, reset

HERO="HHG-001"
SEED_USER={"username":"admin","name":"Admin","role":"admin"}
def seed(conn,*args,**kwargs): return reset(conn)

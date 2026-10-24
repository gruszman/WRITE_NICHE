import time
import subprocess
import os
from datetime import datetime

# Nazwa naszego kontenera
TARGET_NODE = "honeygain_node"

def check_node_status(SerwerDocker01):
    """Sprawdza, czy kontener z węzłem Bandwidth działa."""
    try:
        output = subprocess.check_output("docker ps --format '{{.Names}}'", shell=True).decode()
        return node_name in output
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Błąd sprawdzania statusu: {e}")
        return False

def restart_node(node_name):
    """Automatycznie restartuje węzeł w razie zatrzymania."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Węzeł {node_name} uległ awarii. Inicjuję restart...")
    try:
        os.system(f"docker restart {node_name}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Węzeł pomyślnie zrestartowany.")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Błąd podczas restartu: {e}")

if __name__ == "__main__":
    print("🤖 Watchdog węzła Honeygain uruchomiony. Monitorowanie 24/7 aktywne...")
    
    while True:
        if not check_node_status(TARGET_NODE):
            restart_node(TARGET_NODE)
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Węzeł {TARGET_NODE} zarabia stabilnie.")
            
        # Sprawdzaj stan co 15 minut (900 sekund)
        time.sleep(900)
import os
import sys

# Ensure project root is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.data_sources.synthetic_source import SyntheticDataSource
from core.config import AppConfig

def main():
    config = AppConfig()
    
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    
    csv_path = os.path.join("data", "sample_mission.csv")
    print(f"Generating synthetic telemetry data to {csv_path}...")
    
    source = SyntheticDataSource()
    source.generate_sample_csv(config, csv_path)
    
    print("Done! Generated sample data successfully.")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from config import DependencyConfig

def main():
    config_loader = DependencyConfig()
    parameters = config_loader.load_config()
    config_loader.display_parameters()

if __name__ == "__main__":
    main()
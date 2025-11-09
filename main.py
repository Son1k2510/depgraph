#!/usr/bin/env python3
from config import DependencyConfig
import requests
import os

class DependencyAnalyzer:
    def __init__(self, config): self.config = config
    
    def extract_dependencies(self):
        repo_url = self.config.parameters['repository_url']
        if repo_url.startswith('file://') or not repo_url.startswith('http'):
            return self._extract_from_local(repo_url)
        return self._extract_from_github(repo_url)
    
    def _extract_from_github(self, repo_url):
        owner, repo_name = self._parse_github_url(repo_url)
        for branch in ['main', 'master', 'HEAD']:
            url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/Cargo.toml"
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    return self._parse_cargo_toml(response.text)
            except: continue
        raise Exception("Не удалось загрузить Cargo.toml")
    
    def _extract_from_local(self, repo_path):
        repo_path = repo_path[7:] if repo_path.startswith('file://') else repo_path
        cargo_toml_path = os.path.join(repo_path, 'Cargo.toml')
        if not os.path.exists(cargo_toml_path):
            raise Exception(f"Cargo.toml не найден: {cargo_toml_path}")
        with open(cargo_toml_path, 'r') as f:
            return self._parse_cargo_toml(f.read())
    
    def _parse_github_url(self, url):
        parts = url.strip('/').split('/')
        if 'github.com' not in parts: raise Exception("Некорректный GitHub URL")
        github_index = parts.index('github.com')
        if len(parts) < github_index + 3: raise Exception("URL должен содержать владельца и репозиторий")
        owner, repo = parts[github_index + 1], parts[github_index + 2]
        return owner, repo[:-4] if repo.endswith('.git') else repo
    
    def _parse_cargo_toml(self, content):
        dependencies, in_dependencies = {}, False
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('[') and line.endswith(']'):
                in_dependencies = (line[1:-1] == 'dependencies')
                continue
            if in_dependencies and '=' in line and not line.startswith('#'):
                name, value = line.split('=', 1)
                version = self._extract_version(value.strip())
                if version: dependencies[name.strip()] = version
        return dependencies
    
    def _extract_version(self, value):
        if value.startswith('{') and 'version' in value:
            start = value.find('version') + 7
            value = value[start:].split('=', 1)[1].split(',')[0].split('}')[0].strip()
        version = value.strip('"\' ')
        return version if version and version != '*' else None

def main():
    config_loader = DependencyConfig()
    parameters = config_loader.load_config()
    config_loader.display_parameters()
    
    print("\nЭтап 2: Сбор данных о зависимостях")
    
    analyzer = DependencyAnalyzer(config_loader)
    try:
        dependencies = analyzer.extract_dependencies()
        print(f"\nПрямые зависимости пакета '{parameters['package_name']}':")
        if dependencies:
            for name, version in dependencies.items(): print(f"{name} = \"{version}\"")
            print(f"\nВсего зависимостей: {len(dependencies)}")
        else: print("Зависимости не найдены")
    except Exception as e: print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()
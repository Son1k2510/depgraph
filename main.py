#!/usr/bin/env python3
from config import DependencyConfig
import requests
import os
from collections import defaultdict

class DependencyAnalyzer:
    def __init__(self, config): 
        self.config = config
        self.cache = {}
    
    def extract_dependencies(self):
        repo_url = self.config.parameters['repository_url']
        if self.config.parameters['test_repository_mode']:
            return self._extract_from_test_file(repo_url)
        if repo_url.startswith('file://') or not repo_url.startswith('http'):
            return self._extract_from_local(repo_url)
        return self._extract_from_github(repo_url)
    
    def extract_dependencies_for_package(self, package):
        if package in self.cache:
            return self.cache[package]
            
        if self.config.parameters['test_repository_mode']:
            deps = self._extract_from_test_file(self.config.parameters['repository_url'])
            result = deps.get(package, [])
        else:
            result = self._get_crate_dependencies(package)
        
        self.cache[package] = result
        return result
    
    def _extract_from_github(self, repo_url):
        owner, repo_name = self._parse_github_url(repo_url)
        for branch in ['main', 'master', 'HEAD']:
            url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/Cargo.toml"
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    return self._parse_cargo_toml(response.text)
            except: continue
        raise Exception("Не удалось загрузить Cargo.toml")
    
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
    
    def _get_crate_dependencies(self, crate_name):
        try:
            url = f"https://crates.io/api/v1/crates/{crate_name}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                version = data['crate']['newest_version']
                deps_url = f"https://crates.io/api/v1/crates/{crate_name}/{version}/dependencies"
                deps_response = requests.get(deps_url, timeout=10)
                if deps_response.status_code == 200:
                    deps_data = deps_response.json()
                    return [dep['crate_id'] for dep in deps_data['dependencies']]
            return []
        except Exception as e:
            print(f"Ошибка при получении зависимостей для {crate_name}: {e}")
            return []
    
    def _extract_from_test_file(self, file_path):
        if not os.path.exists(file_path):
            raise Exception(f"Тестовый файл не найден: {file_path}")
        with open(file_path, 'r') as f:
            content = f.read().strip()
        dependencies = {}
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#') and ':' in line:
                pkg, deps = line.split(':', 1)
                dependencies[pkg.strip()] = [d.strip() for d in deps.split(',') if d.strip()]
        return dependencies

    def _extract_from_local(self, repo_path):
        repo_path = repo_path[7:] if repo_path.startswith('file://') else repo_path
        cargo_toml_path = os.path.join(repo_path, 'Cargo.toml')
        if not os.path.exists(cargo_toml_path):
            raise Exception(f"Cargo.toml не найден: {cargo_toml_path}")
        with open(cargo_toml_path, 'r') as f:
            return self._parse_cargo_toml(f.read())

class DependencyGraph:
    def __init__(self, analyzer, config):
        self.analyzer = analyzer
        self.config = config
        self.graph = defaultdict(list)
        self.visited = set()
        self.recursion_stack = set()
        self.cycles = []
    
    def build_complete_graph(self, start_package):
        max_depth = self.config.parameters['max_depth']
        self._dfs(start_package, 0, max_depth, [])
        return self.graph
    
    def _dfs(self, package, current_depth, max_depth, path):
        if current_depth >= max_depth: return
        if package in self.recursion_stack:
            cycle = path[path.index(package):] + [package]
            self.cycles.append(cycle)
            return
        if package in self.visited: return
        
        print(f"Анализируем пакет: {package} (глубина: {current_depth})")
        self.visited.add(package)
        self.recursion_stack.add(package)
        
        try:
            dependencies = self.analyzer.extract_dependencies_for_package(package)
            for dep in dependencies:
                self.graph[package].append(dep)
                self._dfs(dep, current_depth + 1, max_depth, path + [package])
        except Exception as e:
            print(f"Ошибка при анализе {package}: {e}")
        
        self.recursion_stack.remove(package)
    
    def print_graph(self):
        print("\nГраф зависимостей:")
        for package, deps in self.graph.items():
            print(f"{package} -> {', '.join(deps)}" if deps else f"{package} -> (нет зависимостей)")
        
        if self.cycles:
            print("\nОбнаружены циклические зависимости:")
            for i, cycle in enumerate(self.cycles, 1):
                print(f"Цикл {i}: {' -> '.join(cycle)}")
        else:
            print("\nЦиклические зависимости не обнаружены")
    
    def print_ascii_tree(self, start_package):
        if not self.config.parameters['ascii_tree_mode']: return
        print(f"\nДерево зависимостей для {start_package}:")
        self._print_tree_node(start_package, 0, set())
    
    def _print_tree_node(self, package, level, visited):
        if package in visited:
            print("  " * level + f"└── {package} [ЦИКЛ]")
            return
        visited.add(package)
        prefix = "  " * level + ("└── " if level > 0 else "")
        print(prefix + package)
        if package in self.graph:
            deps = self.graph[package]
            for i, dep in enumerate(deps):
                connector = "    " + "  " * level + ("└── " if i == len(deps)-1 else "├── ")
                print(connector, end="")
                self._print_tree_node(dep, level + 1, visited.copy())

def create_test_file():
    test_content = """A:B,C
B:C,D
C:A,E
D:E,F
E:G
F:G
G:
H:I,J
I:H
J:K
K:"""
    with open('test_dependencies.txt', 'w') as f:
        f.write(test_content)
    print("Создан тестовый файл: test_dependencies.txt")

def main():
    config_loader = DependencyConfig()
    parameters = config_loader.load_config()
    config_loader.display_parameters()
    
    if not os.path.exists('test_dependencies.txt'):
        create_test_file()
    
    print("\nЭтап 3: Построение графа зависимостей")
    
    analyzer = DependencyAnalyzer(config_loader)
    graph_builder = DependencyGraph(analyzer, config_loader)
    
    try:
        start_package = parameters['package_name']
        complete_graph = graph_builder.build_complete_graph(start_package)
        
        graph_builder.print_graph()
        graph_builder.print_ascii_tree(start_package)
        
        print(f"\nСтатистика:")
        print(f"Всего пакетов в графе: {len(complete_graph)}")
        print(f"Обнаружено циклов: {len(graph_builder.cycles)}")
        print(f"Максимальная глубина анализа: {parameters['max_depth']}")
        
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()
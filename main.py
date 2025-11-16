#!/usr/bin/env python3
from config import DependencyConfig
import requests
import os
import re
from collections import defaultdict, deque
import subprocess
import json

class DependencyAnalyzer:
    def __init__(self, config): 
        self.config = config
        self.cache = {}
    
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
    
    def _get_crate_dependencies(self, crate_name):
        """Получить зависимости пакета из crates.io"""
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
        """Получить зависимости из тестового файла"""
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

class DependencyGraph:
    def __init__(self, analyzer, config):
        self.analyzer = analyzer
        self.config = config
        self.graph = defaultdict(list)
        self.visited = set()
        self.recursion_stack = set()
        self.cycles = []
    
    def build_complete_graph(self, start_package):
        """Построить полный граф зависимостей с DFS"""
        max_depth = self.config.parameters['max_depth']
        self._dfs(start_package, 0, max_depth, [])
        return self.graph
    
    def _dfs(self, package, current_depth, max_depth, path):
        if current_depth >= max_depth:
            return
            
        # Проверка циклических зависимостей
        if package in self.recursion_stack:
            cycle = path[path.index(package):] + [package]
            self.cycles.append(cycle)
            return
            
        if package in self.visited:
            return
        
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
        """Вывести граф зависимостей"""
        print("\nГраф зависимостей:")
        for package, deps in self.graph.items():
            if deps:
                print(f"{package} -> {', '.join(deps)}")
            else:
                print(f"{package} -> (нет зависимостей)")
        
        if self.cycles:
            print("\nОбнаружены циклические зависимости:")
            for i, cycle in enumerate(self.cycles, 1):
                print(f"Цикл {i}: {' -> '.join(cycle)}")
        else:
            print("\nЦиклические зависимости не обнаружены")
    
    def print_ascii_tree(self, start_package):
        """Вывести дерево в ASCII формате (исправленная версия)"""
        if not self.config.parameters['ascii_tree_mode']:
            return
            
        print(f"\nДерево зависимостей для {start_package}:")
        
        def print_compact_node(package, prefix, is_last, visited):
            if package in visited:
                print(f"{prefix}└── {package} [ПОВТОР]")
                return
                
            visited.add(package)
            
            connector = "└── " if is_last else "├── "
            print(f"{prefix}{connector}{package}")
            
            if package in self.graph and self.graph[package]:
                new_prefix = prefix + ("    " if is_last else "│   ")
                deps = self.graph[package]
                
                for i, dep in enumerate(deps):
                    is_last_dep = (i == len(deps) - 1)
                    print_compact_node(dep, new_prefix, is_last_dep, visited.copy())
        
        print_compact_node(start_package, "", True, set())

    # ЭТАП 4: Порядок загрузки зависимостей
    def get_load_order(self, start_package):
        """Получить порядок загрузки зависимостей (топологическая сортировка)"""
        visited = set()
        stack = []
        temp_visited = set()  # для обнаружения циклов
        
        def topological_sort(package):
            if package in temp_visited:
                return  # Цикл обнаружен, пропускаем
                
            if package in visited:
                return
                
            visited.add(package)
            temp_visited.add(package)
            
            for dep in self.graph.get(package, []):
                topological_sort(dep)
            
            temp_visited.remove(package)
            stack.append(package)
        
        topological_sort(start_package)
        return stack[::-1]
    
    def print_load_order(self, start_package):
        """Вывести порядок загрузки зависимостей"""
        load_order = self.get_load_order(start_package)
        print(f"\nПорядок загрузки зависимостей для '{start_package}':")
        for i, package in enumerate(load_order, 1):
            print(f"{i:2d}. {package}")
        return load_order

class CargoComparator:
    """Сравнение с Cargo (для реальных пакетов)"""
    
    @staticmethod
    def is_cargo_available():
        """Проверить доступность Cargo"""
        try:
            subprocess.run(['cargo', '--version'], capture_output=True, check=True)
            return True
        except:
            return False
    
    @staticmethod
    def get_cargo_tree(package_name):
        """Получить дерево зависимостей через cargo tree"""
        if not CargoComparator.is_cargo_available():
            return None
            
        try:
            temp_dir = f"temp_cargo_{package_name}"
            os.makedirs(temp_dir, exist_ok=True)
            
            cargo_toml = f"""[package]
name = "temp_project"
version = "0.1.0"
edition = "2021"

[dependencies]
{package_name} = "*"
"""
            with open(f"{temp_dir}/Cargo.toml", 'w') as f:
                f.write(cargo_toml)
            
            result = subprocess.run(
                ['cargo', 'tree', '--quiet', '--prefix=none'],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Очистка временной директории
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            if result.returncode == 0:
                return [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            return None
            
        except Exception as e:
            print(f"Ошибка при вызове Cargo: {e}")
            return None
    
    @staticmethod
    def compare_orders(our_order, cargo_output):
        """Сравнить порядки загрузки"""
        if not cargo_output:
            return ["Cargo не установлен или произошла ошибка"]
        
        cargo_packages = []
        for line in cargo_output:
            pkg = line.split()[0] if line.split() else ""
            if pkg and pkg != 'temp_project' and pkg not in cargo_packages:
                cargo_packages.append(pkg)
        
        print(f"\nПорядок загрузки Cargo:")
        for i, pkg in enumerate(cargo_packages, 1):
            print(f"{i:2d}. {pkg}")
        
        differences = []
        
        # Найти различия
        our_missing = set(our_order) - set(cargo_packages)
        if our_missing:
            differences.append(f"В нашем анализе нет: {', '.join(our_missing)}")
        
        cargo_missing = set(cargo_packages) - set(our_order)
        if cargo_missing:
            differences.append(f"В Cargo нет: {', '.join(cargo_missing)}")
        
        # Сравнить порядок для общих пакетов
        common = set(our_order) & set(cargo_packages)
        order_diff = []
        for pkg in common:
            our_pos = our_order.index(pkg)
            cargo_pos = cargo_packages.index(pkg)
            if our_pos != cargo_pos:
                order_diff.append(f"{pkg}: мы={our_pos+1}, cargo={cargo_pos+1}")
        
        if order_diff:
            differences.append("Разный порядок:")
            differences.extend(order_diff)
        
        return differences

def create_test_file():
    """Создать тестовый файл с зависимостями"""
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
    
    print("\n" + "="*60)
    print("ЭТАП 4: ДОПОЛНИТЕЛЬНЫЕ ОПЕРАЦИИ")
    print("="*60)
    
    analyzer = DependencyAnalyzer(config_loader)
    graph_builder = DependencyGraph(analyzer, config_loader)
    
    try:
        start_package = parameters['package_name']
        
        # Построение графа зависимостей
        complete_graph = graph_builder.build_complete_graph(start_package)
        
        # Вывод результатов
        graph_builder.print_graph()
        graph_builder.print_ascii_tree(start_package)
        
        # ЭТАП 4: Порядок загрузки
        print("\n" + "="*50)
        print("ПОРЯДОК ЗАГРУЗКИ ЗАВИСИМОСТЕЙ")
        print("="*50)
        
        our_load_order = graph_builder.print_load_order(start_package)
        
        # Сравнение с Cargo (только для реальных пакетов)
        if not parameters['test_repository_mode']:
            print("\n" + "="*50)
            print("СРАВНЕНИЕ С CARGO")
            print("="*50)
            
            cargo_output = CargoComparator.get_cargo_tree(start_package)
            differences = CargoComparator.compare_orders(our_load_order, cargo_output)
            
            if differences:
                print("\nОбнаружены расхождения:")
                for diff in differences:
                    print(f"  - {diff}")
                print("\nПричины расхождений:")
                print("  1. Cargo учитывает версии и features")
                print("  2. Наш анализ использует статические данные crates.io")
                print("  3. Cargo обрабатывает условные зависимости")
            else:
                print("\nПорядки загрузки совпадают!")
        
        # Статистика анализа
        print("\n" + "="*50)
        print("СТАТИСТИКА АНАЛИЗА")
        print("="*50)
        print(f"Начальный пакет: {start_package}")
        print(f"Всего пакетов в графе: {len(complete_graph)}")
        print(f"Обнаружено циклов: {len(graph_builder.cycles)}")
        print(f"Максимальная глубина анализа: {parameters['max_depth']}")
        
    except Exception as e:
        print(f"\nОшибка: {e}")

if __name__ == "__main__":
    main()
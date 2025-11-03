import configparser

class DependencyConfig:
    def __init__(self, config_file="config.ini"):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.parameters = {}
        
    def load_config(self):
        self.config.read(self.config_file)
        
        self.parameters['package_name'] = self.config.get('DEFAULT', 'package_name')
        self.parameters['repository_url'] = self.config.get('DEFAULT', 'repository_url')
        self.parameters['output_filename'] = self.config.get('DEFAULT', 'output_filename')
        
        test_mode = self.config.get('DEFAULT', 'test_repository_mode')
        self.parameters['test_repository_mode'] = test_mode.lower() in ('true', 'yes', '1')
        
        ascii_mode = self.config.get('DEFAULT', 'ascii_tree_mode')
        self.parameters['ascii_tree_mode'] = ascii_mode.lower() in ('true', 'yes', '1')
        
        self.parameters['max_depth'] = int(self.config.get('DEFAULT', 'max_depth'))
        
        return self.parameters
    
    def display_parameters(self):
        for key, value in self.parameters.items():
            print(f"{key}: {value}")
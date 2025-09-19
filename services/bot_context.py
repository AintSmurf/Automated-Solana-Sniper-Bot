
class BotContext:
    def __init__(self, settings, api_keys: dict, settings_manager,first_run):
        self.services = {}
        self.settings_manager = settings_manager
        self.settings = settings
        self.api_keys = api_keys
        self.first_run = first_run

    def register(self, name: str, service: object):
        self.services[name] = service

    def get(self, name: str):
        return self.services.get(name)
    
    def __contains__(self, name: str):
        return name in self.services
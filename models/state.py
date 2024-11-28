class SimulationState:
    """Singleton class to store the state of the simulation environment."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.generators = []
            cls._instance.collectors = []
            cls._instance.treatment_operators = []
        return cls._instance

    @classmethod
    def get_instance(cls):
        return cls() if cls._instance is None else cls._instance

    def initialize(self, generators, collectors, treatment_operators):
        self.generators = generators
        self.collectors = collectors
        self.treatment_operators = treatment_operators

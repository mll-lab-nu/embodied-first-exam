from control_public.weights import Network


class Policy(Network):
    def __init__(self, path, robot):
        if robot != "linearbot":
            raise ValueError("Unsupported robot")
        super().__init__(path, "linearbot")
        self.mean = self.a["mean"]
        self.std = self.a["std"]
        self.layers = [(self.a[f"w{i}"], self.a[f"b{i}"]) for i in range(3)]

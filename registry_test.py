from simulation.tools.registry import ToolRegistry


def main():

    registry = ToolRegistry()

    print()

    print("===================================")
    print(" TOOL REGISTRY")
    print("===================================")

    for tool in registry.list_tools():

        print()

        print(f"Name        : {tool['name']}")
        print(f"Description : {tool['description']}")
        print(f"Version     : {tool['version']}")

    print()
    print("===================================")


if __name__ == "__main__":

    main()